import smtplib
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from html import escape
from urllib.parse import urlencode

from celery import shared_task
from sqlalchemy import or_, select

from app.core.config import settings
from app.db.database import SessionLocal
from app.models.content_draft import ContentDraft
from app.models.research_item import ResearchItem
from app.models.social_connection import SocialConnection
from app.models.topic import Topic
from app.services.ai_service import generate_content
from app.services.ai_service import AIServiceError
from app.services.approval_service import create_approval_token
from app.services.social_integration import _media_part


def _select_top_research(limit: int = 5) -> list[tuple[Topic, ResearchItem]]:
    db = SessionLocal()
    try:
        today = datetime.now(timezone.utc)
        frequency_filter = [Topic.research_frequency == "daily"]
        if today.weekday() == 0:
            frequency_filter.append(Topic.research_frequency == "weekly")
        if today.day == 1:
            frequency_filter.append(Topic.research_frequency == "monthly")

        rows = db.execute(
            select(Topic, ResearchItem)
            .join(ResearchItem, ResearchItem.topic_id == Topic.id)
            .where(
                Topic.active.is_(True),
                or_(*frequency_filter),
            )
            .order_by(ResearchItem.relevance_score.desc(), ResearchItem.published_at.desc())
            .limit(limit)
        ).all()
        return [(topic, item) for topic, item in rows]
    finally:
        db.close()


def _approval_platform(db) -> str:
    connected_provider = db.scalar(
        select(SocialConnection.provider)
        .where(SocialConnection.status == "connected")
        .order_by(
            (SocialConnection.provider == "facebook").desc(),
            SocialConnection.created_at.desc(),
        )
    )
    return connected_provider or "linkedin"


def _build_digest_email_body(drafts: list[ContentDraft]) -> tuple[str, str]:
    items = []
    for draft in drafts:
        token = create_approval_token(str(draft.id), "approve")
        approval_url = f"{settings.app_base_url}/api/v1/approvals/preview?token={token}"
        media_html = ""
        media = _media_part(draft)
        if media:
            media_html = f'<img src="cid:{media[0]}" alt="Post media" style="display:block; width:100%; max-height:260px; object-fit:cover; border-radius:8px; margin:0 0 12px;" />'
        items.append(
            f"<li style='margin-bottom:16px; padding:14px 16px; border:1px solid #164e63; border-radius:10px; background:#0f172a;'>"
            f"{media_html}"
            f"<div style='font-weight:700; margin-bottom:8px;'>{escape(draft.platform)}</div>"
            f"<div style='margin-bottom:12px; color:#cbd5e1;'>{escape(draft.content[:180])}{'...' if len(draft.content) > 180 else ''}</div>"
            f"<a href='{approval_url}' style='display:inline-block; background:#22c55e; color:#04130c; text-decoration:none; padding:10px 16px; border-radius:8px; font-weight:700;'>Approve & post</a>"
            f"</li>"
        )

    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; background:#07131f; color:#e2e8f0; padding:32px;">
        <div style="max-width:760px; margin:0 auto; background:#020817; border:1px solid #164e63; border-radius:16px; padding:24px;">
          <h2 style="margin-top:0;">PostMesh daily topic options</h2>
          <p>Choose one of the top five topic suggestions below. Each option opens a review page so you can edit before approving.</p>
          <ul style="list-style:none; padding:0; margin:20px 0 0;">
            {''.join(items)}
          </ul>
        </div>
      </body>
    </html>
    """
    plain = "PostMesh daily topic options\n\n" + "\n".join(
        f"- {draft.platform}: {draft.content[:160]}" for draft in drafts
    )
    return plain, html


@shared_task(name="app.tasks.daily_approvals.send_daily_approval_options")
def send_daily_approval_options() -> dict[str, object]:
    """Send one digest email with the best topic options and direct review links."""
    recipient = settings.default_approval_email or settings.email_from or "admin@example.com"
    top_research = _select_top_research(limit=5)
    if not top_research:
        return {"status": "skipped", "reason": "No active topics found"}

    db = SessionLocal()
    try:
        drafts: list[ContentDraft] = []
        for topic, item in top_research:
            platform = topic.posting_platform
            try:
                content, _model_name = generate_content(
                    research_item=item,
                    platform=platform,
                    topic_name=topic.name,
                    db=db,
                )
            except AIServiceError:
                continue

            draft = ContentDraft(
                topic_id=topic.id,
                research_item_id=item.id,
                platform=platform,
                approval_channel="email",
                approval_email=recipient,
                approval_recipient=None,
                approval_whatsapp=None,
                status="draft",
                content=content,
                media_url=(
                    "/api/v1/media/auto?"
                    + urlencode(
                        {
                            "topic": topic.name,
                            "title": item.title,
                            "source": item.source,
                            "article_url": item.url,
                        }
                    )
                ),
                model_name=_model_name,
            )
            db.add(draft)
            db.flush()
            drafts.append(draft)

        db.commit()

        if not drafts:
            return {"status": "skipped", "reason": "No drafts generated for top topics"}

        plain_text, html_body = _build_digest_email_body(drafts)
        message = EmailMessage()
        message["Subject"] = "PostMesh: top 5 topic options for approval"
        message["From"] = settings.email_from or recipient
        message["To"] = recipient
        message.set_content(plain_text)
        message.add_alternative(html_body, subtype="html")
        html_part = message.get_body(preferencelist=("html",))
        for draft in drafts:
            media = _media_part(draft)
            if media and html_part is not None:
                cid, data, maintype, subtype = media
                html_part.add_related(data, maintype=maintype, subtype=subtype, cid=f"<{cid}>")

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port or 587) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_username and settings.smtp_password:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)

        return {
            "status": "sent",
            "recipient": recipient,
            "topic_count": len(drafts),
            "draft_ids": [str(draft.id) for draft in drafts],
        }
    finally:
        db.close()
