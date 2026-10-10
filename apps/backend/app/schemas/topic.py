import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TopicCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    keywords: list[str] = Field(default_factory=list)
    active: bool = True
    research_frequency: str = "daily"


class TopicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    keywords: list[str]
    active: bool
    research_frequency: str
    created_at: datetime
    updated_at: datetime
