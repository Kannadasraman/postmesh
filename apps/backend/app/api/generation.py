import uuid
from datetime import datetime, timezone
from urllib.parse import quote_plus

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.content_draft import ContentDraft
from app.models.publishing_job import PublishingJob
from app.models.research_item import ResearchItem
from app.models.topic import Topic
from app.schemas.content_draft import (
    ContentDraftResponse,
    DraftGenerateRequest,
    DraftStatusUpdateRequest,
    DraftUpdateRequest,
)
from app.services.ai_service import (
    AIServiceError,
    generate_content,
)

router = APIRouter(
    tags=["AI Generation"],
)


@router.post(
    "/api/v1/research/{research_item_id}/generate",
    response_model=ContentDraftResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_draft(
    research_item_id: uuid.UUID,
    payload: DraftGenerateRequest,
    db: Session = Depends(get_db),
):
    research_item = db.get(
        ResearchItem,
        research_item_id,
    )

    if research_item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research item not found",
        )

    topic = db.get(
        Topic,
        research_item.topic_id,
    )

    if topic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found",
        )

    try:
        content, model_name = (
            generate_content(
                research_item=research_item,
                platform=payload.platform,
                topic_name=topic.name,
                db=db,
            )
        )

    except AIServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    draft = ContentDraft(
        topic_id=research_item.topic_id,
        research_item_id=research_item.id,
        platform=payload.platform,
        approval_channel=payload.approval_channel,
        approval_recipient=payload.approval_recipient,
        approval_email=payload.approval_email,
        approval_whatsapp=payload.approval_whatsapp,
        status="draft",
        content=content,
        media_url=(
            f"/api/v1/media/auto?topic={quote_plus(topic.name)}"
        ),
        model_name=model_name,
    )

    db.add(draft)
    db.commit()
    db.refresh(draft)

    if payload.approval_channel not in {"in_app", None}:
        try:
            from app.services.social_integration import send_approval_request

            send_approval_request(
                draft,
                payload.approval_channel,
                payload.approval_recipient,
                email_recipient=payload.approval_email,
                whatsapp_recipient=payload.approval_whatsapp,
            )
        except Exception as exc:  # pragma: no cover - runtime integration path
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Approval request could not be sent: {exc}",
            ) from exc

    return draft


@router.get(
    "/api/v1/topics/{topic_id}/drafts",
    response_model=list[
        ContentDraftResponse
    ],
)
def list_topic_drafts(
    topic_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    topic = db.get(
        Topic,
        topic_id,
    )

    if topic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found",
        )

    drafts = db.scalars(
        select(ContentDraft)
        .where(
            ContentDraft.topic_id
            == topic_id,
        )
        .order_by(
            ContentDraft.updated_at.desc(),
        )
    ).all()

    return list(drafts)


@router.patch(
    "/api/v1/drafts/{draft_id}",
    response_model=ContentDraftResponse,
)
def update_draft(
    draft_id: uuid.UUID,
    payload: DraftUpdateRequest,
    db: Session = Depends(get_db),
):
    draft = db.get(
        ContentDraft,
        draft_id,
    )

    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Draft not found",
        )

    content = (
        payload.content.strip()
    )

    if not content:
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail="Draft content cannot be empty",
        )

    draft.content = content

    if draft.status in {
        "approved",
        "rejected",
    }:
        draft.status = "draft"

    db.commit()
    db.refresh(draft)

    return draft


@router.patch(
    "/api/v1/drafts/{draft_id}/status",
    response_model=ContentDraftResponse,
)
def update_draft_status(
    draft_id: uuid.UUID,
    payload: DraftStatusUpdateRequest,
    db: Session = Depends(get_db),
):
    draft = db.get(
        ContentDraft,
        draft_id,
    )

    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Draft not found",
        )

    draft.status = payload.status

    if payload.review_notes is not None:
        draft.review_notes = payload.review_notes.strip() or None

    draft.request_next_post = bool(payload.request_next_post)

    if payload.status == "approved":
        active_job = db.scalar(
            select(PublishingJob)
            .where(
                PublishingJob.draft_id == draft.id,
                PublishingJob.status.in_(
                    ("scheduled", "queued", "publishing", "published")
                ),
            )
        )

        if active_job is None:
            db.add(
                PublishingJob(
                    draft_id=draft.id,
                    platform=draft.platform,
                    status="scheduled",
                    content_snapshot=draft.content,
                    scheduled_at=datetime.now(timezone.utc),
                    max_attempts=3,
                )
            )

    db.commit()
    db.refresh(draft)

    if payload.status == "rejected" and payload.request_next_post:
        research_item = db.get(ResearchItem, draft.research_item_id)
        topic = db.get(Topic, draft.topic_id)

        if research_item is None or topic is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Research item or topic not found for next draft",
            )

        try:
            next_content, next_model_name = generate_content(
                research_item=research_item,
                platform=draft.platform,
                topic_name=topic.name,
                db=db,
            )
            next_draft = ContentDraft(
                topic_id=draft.topic_id,
                research_item_id=draft.research_item_id,
                platform=draft.platform,
                approval_channel=draft.approval_channel,
                approval_recipient=draft.approval_recipient,
                approval_email=draft.approval_email,
                approval_whatsapp=draft.approval_whatsapp,
                status="draft",
                content=next_content,
                media_url=draft.media_url,
                model_name=next_model_name,
            )
            db.add(next_draft)
            db.commit()
            db.refresh(next_draft)

            if next_draft.approval_channel not in {"in_app", None}:
                from app.services.social_integration import send_approval_request

                send_approval_request(
                    next_draft,
                    next_draft.approval_channel,
                    next_draft.approval_recipient,
                    email_recipient=next_draft.approval_email,
                    whatsapp_recipient=next_draft.approval_whatsapp,
                )
        except Exception as exc:  # pragma: no cover - runtime integration path
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Next draft could not be generated: {exc}",
            ) from exc

    return draft
