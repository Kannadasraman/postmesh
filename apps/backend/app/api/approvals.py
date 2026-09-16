import uuid
from datetime import datetime, timezone
from html import escape
from urllib.parse import urljoin

from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.models.content_draft import ContentDraft
from app.models.publishing_job import PublishingJob
from app.services.approval_service import decode_approval_token
from app.services.publishing_service import execute_publishing_job

router = APIRouter(prefix="/api/v1/approvals", tags=["Approvals"])


def _get_draft_for_token(token: str, db: Session) -> ContentDraft:
    payload = decode_approval_token(token)
    draft_id = uuid.UUID(str(payload["draft_id"]))
    draft = db.get(ContentDraft, draft_id)
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
    return draft


def _render_approval_form(draft: ContentDraft, token: str, action: str) -> str:
    escaped = (draft.content or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    media_html = ""
    if draft.media_url:
        media_url = urljoin(settings.app_base_url, draft.media_url)
        media_html = f'<img src="{escape(media_url, quote=True)}" alt="Post media" style="display:block; width:100%; max-height:420px; object-fit:cover; border-radius:12px; margin:18px 0;" />'
    return f"""
    <html>
      <body style="font-family: Arial, sans-serif; background:#07131f; color:#e2e8f0; padding:40px;">
        <div style="max-width:760px; margin:0 auto; background:#0f172a; border:1px solid #164e63; border-radius:16px; padding:24px;">
          <h2 style="margin-top:0;">PostMesh approval</h2>
          <p>Platform: {draft.platform}</p>
          {media_html}
          <form method="post" action="/api/v1/approvals/approve">
            <input type="hidden" name="token" value="{token}" />
            <textarea name="content" rows="18" style="width:100%; border-radius:12px; padding:16px; background:#020817; color:#e2e8f0; border:1px solid #334155; box-sizing:border-box;">{escaped}</textarea>
            <div style="display:flex; gap:12px; margin-top:16px;">
              <button type="submit" name="action" value="approve" style="background:#22c55e; color:#04130c; font-weight:700; border:none; border-radius:10px; padding:12px 18px; cursor:pointer;">Approve and post</button>
              <button type="submit" name="action" value="reject" style="background:#ef4444; color:white; font-weight:700; border:none; border-radius:10px; padding:12px 18px; cursor:pointer;">Reject</button>
            </div>
          </form>
        </div>
      </body>
    </html>
    """


@router.get("/preview")
def preview_approval(token: str, db: Session = Depends(get_db)):
    try:
        draft = _get_draft_for_token(token, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return HTMLResponse(_render_approval_form(draft, token, "approve"))


@router.post("/approve")
def approve_from_email(
    token: str = Form(...),
    content: str | None = Form(default=None),
    action: str = Form("approve"),
    db: Session = Depends(get_db),
):
    try:
        payload = decode_approval_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    draft_id = uuid.UUID(str(payload["draft_id"]))
    draft = db.get(ContentDraft, draft_id)
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")

    if action == "reject":
        draft.status = "rejected"
        db.commit()
        return {"status": "rejected", "draft_id": str(draft.id)}

    new_content = (content or draft.content).strip()
    if not new_content:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Draft content cannot be empty")

    draft.content = new_content
    draft.status = "approved"
    db.commit()
    db.refresh(draft)

    job = db.scalar(
        select(PublishingJob)
        .where(
            PublishingJob.draft_id == draft.id,
            PublishingJob.status.in_(("scheduled", "queued", "publishing", "published")),
        )
        .order_by(PublishingJob.created_at.desc())
    )

    if job is None:
        now = datetime.now(timezone.utc)
        job = PublishingJob(
            draft_id=draft.id,
            platform=draft.platform,
            status="queued",
            content_snapshot=draft.content,
            scheduled_at=now,
            queued_at=now,
            max_attempts=1,
        )
        db.add(job)
        db.commit()
        db.refresh(job)

    execute_publishing_job(draft, job)
    db.commit()
    db.refresh(job)

    if job.status == "failed":
        return {
            "status": "approved_but_publish_failed",
            "draft_id": str(draft.id),
            "job_id": str(job.id),
            "error": job.last_error,
        }

    return {"status": "approved_and_published", "draft_id": str(draft.id), "job_id": str(job.id)}


@router.post("/reject")
def reject_from_email(token: str = Form(...), db: Session = Depends(get_db)):
    return approve_from_email(token=token, content=None, action="reject", db=db)
