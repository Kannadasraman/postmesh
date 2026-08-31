import uuid
from html import escape
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.content_draft import ContentDraft

router = APIRouter(tags=["Draft media"])
UPLOAD_DIR = Path("/app/uploads")
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


@router.get("/api/v1/media/auto")
def automatic_media(topic: str = Query(default="Industry News", max_length=120)):
        safe_topic = escape(topic.strip() or "Industry News")
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
            <defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#082f49"/><stop offset="1" stop-color="#164e63"/></linearGradient></defs>
            <rect width="1200" height="630" fill="url(#bg)"/>
            <circle cx="1020" cy="100" r="230" fill="#22d3ee" opacity=".16"/>
            <circle cx="1080" cy="570" r="300" fill="#67e8f9" opacity=".10"/>
            <path d="M0 500 C260 390 390 600 650 470 S980 370 1200 430 V630 H0Z" fill="#020617" opacity=".55"/>
            <text x="72" y="170" fill="#67e8f9" font-family="sans-serif" font-size="26" font-weight="700" letter-spacing="3">POSTMESH NEWS</text>
            <text x="72" y="270" fill="white" font-family="sans-serif" font-size="58" font-weight="700">{safe_topic}</text>
            <text x="72" y="330" fill="#bae6fd" font-family="sans-serif" font-size="30">Latest relevant story</text>
            <rect x="72" y="430" width="150" height="8" rx="4" fill="#22d3ee"/>
        </svg>'''
        return Response(content=svg, media_type="image/svg+xml")


draft_router = APIRouter(prefix="/api/v1/drafts", tags=["Draft media"])


@draft_router.post("/{draft_id}/media", status_code=status.HTTP_200_OK)
async def upload_draft_media(
    draft_id: uuid.UUID,
    file: UploadFile,
    db: Session = Depends(get_db),
):
    draft = db.get(ContentDraft, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="Upload a JPG, PNG, WebP, or GIF image")

    suffix = Path(file.filename or "image").suffix.lower() or ".jpg"
    filename = f"{draft_id}{suffix}"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    target = UPLOAD_DIR / filename
    target.write_bytes(await file.read())
    draft.media_url = f"/uploads/{filename}"
    db.commit()
    db.refresh(draft)
    return {"media_url": draft.media_url}