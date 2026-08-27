import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.topic import Topic
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
) -> Topic:
    topic = db.get(Topic, topic_id)

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
):
    topic = get_topic_or_404(topic_id, db)

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
):
    topic = get_topic_or_404(topic_id, db)

    return get_research(
        db=db,
        topic=topic,
    )
