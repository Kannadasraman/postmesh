import uuid
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.content_draft import ContentDraft
from app.services.evidence_service import _resolve_source_url, _safe_public_url

router = APIRouter(tags=["Draft media"])
UPLOAD_DIR = Path("/app/uploads")
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PostMesh/0.5; +https://postmesh.local)",
}


class _OpenGraphImageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.image_url = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta" or self.image_url:
            return

        values = {
            key.lower(): (value or "").strip()
            for key, value in attrs
        }
        image_key = (
            values.get("property")
            or values.get("name")
            or ""
        ).lower()
        if image_key in {"og:image", "og:image:url", "twitter:image"}:
            self.image_url = values.get("content", "")


def _article_image_url(article_url: str) -> str | None:
    if not article_url or not _safe_public_url(article_url):
        return None

    resolved_url, _ = _resolve_source_url(article_url)
    if not _safe_public_url(resolved_url):
        return None

    try:
        response = httpx.get(
            resolved_url,
            headers=REQUEST_HEADERS,
            follow_redirects=True,
            timeout=12.0,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return None

    if "html" not in response.headers.get("content-type", "").lower():
        return None

    parser = _OpenGraphImageParser()
    try:
        parser.feed(response.text[:1_000_000])
    except (ValueError, UnicodeError):
        return None

    image_url = urljoin(str(response.url), parser.image_url)
    return image_url if _safe_public_url(image_url) else None


def _headline_lines(title: str, max_lines: int = 3) -> list[str]:
    words = title.split()
    lines: list[str] = []
    current = ""

    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > 34 and current:
            lines.append(current)
            current = word
            if len(lines) == max_lines:
                break
        else:
            current = candidate

    if current and len(lines) < max_lines:
        lines.append(current)

    return lines or ["Latest story"]


def _story_fallback_image(topic: str, title: str, source: str) -> Response:
    safe_topic = escape(topic.strip() or "Industry News")
    safe_source = escape(source.strip() or "PostMesh Research")
    title_svg = "".join(
        f'<text x="72" y="{250 + index * 62}" fill="white" '
        f'font-family="sans-serif" font-size="46" font-weight="700">{escape(line)}</text>'
        for index, line in enumerate(_headline_lines(title.strip()))
    )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
        <defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#082f49"/><stop offset="1" stop-color="#164e63"/></linearGradient></defs>
        <rect width="1200" height="630" fill="url(#bg)"/>
        <circle cx="1020" cy="100" r="230" fill="#22d3ee" opacity=".16"/>
        <path d="M0 500 C260 390 390 600 650 470 S980 370 1200 430 V630 H0Z" fill="#020617" opacity=".55"/>
        <text x="72" y="112" fill="#67e8f9" font-family="sans-serif" font-size="24" font-weight="700" letter-spacing="3">{safe_source.upper()}</text>
        <text x="72" y="164" fill="#bae6fd" font-family="sans-serif" font-size="26">{safe_topic}</text>
        {title_svg}
        <rect x="72" y="548" width="150" height="8" rx="4" fill="#22d3ee"/>
    </svg>'''
    return Response(content=svg, media_type="image/svg+xml")


@router.get("/api/v1/media/auto")
def automatic_media(
    topic: str = Query(default="Industry News", max_length=120),
    title: str = Query(default="", max_length=500),
    source: str = Query(default="", max_length=100),
    article_url: str = Query(default="", max_length=2_000),
):
    """Use the article's editorial image; only use a headline card as a safe fallback."""
    image_url = _article_image_url(article_url)
    if image_url:
        return RedirectResponse(url=image_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    return _story_fallback_image(topic, title, source)


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
