import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


Platform = Literal[
    "linkedin",
    "x",
    "facebook",
    "blog",
]


class DraftGenerateRequest(BaseModel):
    platform: Platform = "linkedin"


class ContentDraftResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    topic_id: uuid.UUID
    research_item_id: uuid.UUID

    platform: str
    status: str
    content: str
    model_name: str

    created_at: datetime
    updated_at: datetime