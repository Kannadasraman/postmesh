import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Platform = Literal[
    "linkedin",
    "x",
    "facebook",
    "blog",
]

DraftStatus = Literal[
    "draft",
    "approved",
    "rejected",
]


class DraftGenerateRequest(BaseModel):
    platform: Platform = "linkedin"


class DraftUpdateRequest(BaseModel):
    content: str = Field(
        min_length=1,
        max_length=20000,
    )


class DraftStatusUpdateRequest(BaseModel):
    status: Literal[
        "approved",
        "rejected",
    ]


class ContentDraftResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID
    topic_id: uuid.UUID
    research_item_id: uuid.UUID

    platform: str
    status: DraftStatus
    content: str
    model_name: str

    created_at: datetime
    updated_at: datetime