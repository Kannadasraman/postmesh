import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ResearchItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    topic_id: uuid.UUID
    title: str
    url: str
    source: str
    summary: str | None
    published_at: datetime | None
    relevance_score: float
    created_at: datetime
