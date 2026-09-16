import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.database import get_db
from app.models.topic import Topic
from app.models.user import User
from app.schemas.research import ResearchItemResponse
from app.services.research_service import (
    get_research,
    run_research,
)


router = APIRouter(
    prefix="/api/v1/topics/{topic_id}/research",
    tags=["Research"],
)


def get_topic_or_404(
    topic_id: uuid.UUID,
    db: Session,
    user: User,
) -> Topic:
    topic = db.scalar(select(Topic).where(Topic.id == topic_id, Topic.user_id == user.id))

    if topic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found",
        )

    return topic


@router.post(
    "",
    response_model=list[ResearchItemResponse],
)
def research_topic(
    topic_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    topic = get_topic_or_404(topic_id, db, user)

    return run_research(
        db=db,
        topic=topic,
    )


@router.get(
    "",
    response_model=list[ResearchItemResponse],
)
def list_research(
    topic_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    topic = get_topic_or_404(topic_id, db, user)

    return get_research(
        db=db,
        topic=topic,
    )
