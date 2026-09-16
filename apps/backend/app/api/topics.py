import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.database import get_db
from app.models.topic import Topic
from app.models.user import User
from app.schemas.topic import TopicCreate, TopicResponse


router = APIRouter(
    prefix="/api/v1/topics",
    tags=["Topics"],
)


def topic_to_response(topic: Topic) -> TopicResponse:
    keywords = []

    if topic.keywords:
        keywords = [
            keyword.strip()
            for keyword in topic.keywords.split(",")
            if keyword.strip()
        ]

    return TopicResponse(
        id=topic.id,
        name=topic.name,
        keywords=keywords,
        active=topic.active,
        research_frequency=topic.research_frequency,
        posting_platform=topic.posting_platform,
        approval_email=topic.approval_email,
        created_at=topic.created_at,
        updated_at=topic.updated_at,
    )


@router.post(
    "",
    response_model=TopicResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_topic(
    payload: TopicCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    topic = Topic(
        user_id=user.id,
        name=payload.name,
        keywords=", ".join(payload.keywords),
        active=payload.active,
        research_frequency=payload.research_frequency,
        posting_platform=payload.posting_platform,
        approval_email=str(payload.approval_email) if payload.approval_email else None,
    )

    db.add(topic)
    db.commit()
    db.refresh(topic)

    return topic_to_response(topic)


@router.get(
    "",
    response_model=list[TopicResponse],
)
def list_topics(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    topics = db.scalars(
        select(Topic).where(Topic.user_id == user.id).order_by(Topic.created_at.desc())
    ).all()

    return [topic_to_response(topic) for topic in topics]


@router.delete(
    "/{topic_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_topic(
    topic_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    topic = db.scalar(select(Topic).where(Topic.id == topic_id, Topic.user_id == user.id))

    if topic is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found",
        )

    db.delete(topic)
    db.commit()
