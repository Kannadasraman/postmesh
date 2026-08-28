import uuid

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
        status="draft",
        content=content,
        model_name=model_name,
    )

    db.add(draft)
    db.commit()
    db.refresh(draft)

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

    db.commit()
    db.refresh(draft)

    return draft