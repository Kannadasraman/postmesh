import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Platform = Literal[
    "linkedin",
    "x",
    "facebook",
    "instagram",
    "threads",
    "youtube",
    "reddit",
    "whatsapp",
    "email",
    "blog",
]

DraftStatus = Literal[
    "draft",
    "approved",
    "rejected",
]


class DraftGenerateRequest(BaseModel):
    platform: Platform = "linkedin"
    approval_channel: Literal["in_app", "whatsapp", "email", "both"] = "in_app"
    approval_recipient: str | None = None
    approval_email: str | None = None
    approval_whatsapp: str | None = None


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
    review_notes: str | None = Field(
        default=None,
        max_length=5000,
    )
    request_next_post: bool = False


class ContentDraftResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID
    topic_id: uuid.UUID
    research_item_id: uuid.UUID

    platform: str
    status: DraftStatus
    approval_channel: str | None = None
    approval_recipient: str | None = None
    approval_email: str | None = None
    approval_whatsapp: str | None = None
    review_notes: str | None = None
    request_next_post: bool = False
    content: str
    media_url: str | None = None
    model_name: str

    created_at: datetime
    updated_at: datetime