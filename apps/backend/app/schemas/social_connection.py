import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Provider = Literal["linkedin", "x", "facebook", "instagram", "threads", "youtube", "reddit", "blog"]


class SocialConnectionCreate(BaseModel):
    provider: Provider
    account_name: str = Field(min_length=1, max_length=255)
    access_token: str | None = Field(default=None, min_length=1)
    api_url: str | None = None


class SocialConnectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    account_name: str
    account_id: str | None
    api_url: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class OAuthCallback(BaseModel):
    code: str
    state: str