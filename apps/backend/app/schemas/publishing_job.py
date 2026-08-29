import uuid
from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.schemas.content_draft import Platform


PublishingStatus = Literal[
    "scheduled",
    "queued",
    "publishing",
    "published",
    "failed",
    "cancelled",
]


class PublishingScheduleRequest(BaseModel):
    scheduled_at: datetime

    max_attempts: int = Field(
        default=3,
        ge=1,
        le=10,
    )

    @field_validator(
        "scheduled_at",
    )
    @classmethod
    def scheduled_at_requires_timezone(
        cls,
        value: datetime,
    ) -> datetime:
        if (
            value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                "scheduled_at must include a timezone offset"
            )

        return value


class PublishingJobResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID
    draft_id: uuid.UUID

    platform: Platform
    status: PublishingStatus
    content_snapshot: str

    scheduled_at: datetime

    attempt_count: int
    max_attempts: int

    queued_at: datetime | None
    started_at: datetime | None
    published_at: datetime | None
    failed_at: datetime | None
    cancelled_at: datetime | None

    external_post_id: str | None
    external_post_url: str | None
    last_error: str | None

    created_at: datetime
    updated_at: datetime
