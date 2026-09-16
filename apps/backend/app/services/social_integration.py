import smtplib
from email.message import EmailMessage
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx
from cryptography.fernet import Fernet

from app.core.config import settings
from app.db.database import SessionLocal
from app.models.social_connection import SocialConnection
from app.services.approval_service import create_approval_token

UPLOAD_DIR = Path("/app/uploads")


def _media_part(draft: Any) -> tuple[str, bytes, str, str] | None:
    media_url = getattr(draft, "media_url", None)
    if not media_url:
        return None

    try:
        if media_url.startswith("/uploads/"):
            media_path = UPLOAD_DIR / Path(media_url).name
            media_type = {
                ".png": "image/png",
                ".webp": "image/webp",
                ".gif": "image/gif",
            }.get(media_path.suffix.lower(), "image/jpeg")
            maintype, subtype = media_type.split("/", 1)
            return f"postmesh-media-{draft.id}", media_path.read_bytes(), maintype, subtype

        media_target = urljoin(settings.app_base_url, media_url)
        if media_target.startswith("http://localhost:8002/"):
            media_target = media_target.replace("http://localhost:8002/", "http://backend:8000/", 1)
        response = httpx.get(
            media_target,
            follow_redirects=True,
            timeout=15,
        )
        response.raise_for_status()
        media_type = response.headers.get("content-type", "").split(";", 1)[0]
        if not media_type.startswith("image/"):
            return None
        maintype, subtype = media_type.split("/", 1)
        return f"postmesh-media-{draft.id}", response.content, maintype, subtype
    except (OSError, httpx.HTTPError, ValueError):
        return None


def _build_review_message(draft: Any, action: str) -> tuple[str, str]:
    recipient_label = draft.approval_channel or "in_app"
    token = create_approval_token(str(draft.id), "approve")
    approval_url = f"{settings.app_base_url}/api/v1/approvals/preview?token={token}"

    lines = [
        f"PostMesh approval update: {action.upper()}",
        "",
        f"Draft ID: {draft.id}",
        f"Platform: {draft.platform}",
        f"Approval channel: {recipient_label}",
        "",
        "Review and approve this draft here:",
        approval_url,
    ]

    if getattr(draft, "review_notes", None):
        lines.extend(["", "Reviewer notes:", draft.review_notes])

    if getattr(draft, "request_next_post", False):
        lines.extend(["", "Requested follow-up: Generate the next post."])

    lines.extend([
        "",
        "Content:",
        draft.content,
    ])

    media_html = ""
    media = _media_part(draft)
    if media:
        media_html = (
            f'<img src="cid:{media[0]}" alt="Post media" '
            'style="display:block; width:100%; max-height:420px; object-fit:cover; '
            'border-radius:12px; margin:18px 0;" />'
        )

    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; background:#07131f; color:#e2e8f0; padding:24px;">
        <div style="max-width:700px; margin:0 auto; background:#0f172a; border:1px solid #164e63; border-radius:16px; padding:24px;">
          <h2 style="margin:0 0 12px;">PostMesh approval update</h2>
          <p><strong>Draft ID:</strong> {draft.id}</p>
          <p><strong>Platform:</strong> {draft.platform}</p>
          <p><strong>Approval channel:</strong> {recipient_label}</p>
          <p>
            <a href="{approval_url}" style="display:inline-block; background:#22c55e; color:#04130c; text-decoration:none; padding:12px 18px; border-radius:10px; font-weight:700;">Review and approve</a>
          </p>
          {media_html}
          <p style="margin-top:20px; color:#cbd5e1; white-space:pre-wrap;">{escape(draft.content)}</p>
        </div>
      </body>
    </html>
    """

    return "\n".join(lines), html


def send_approval_request(draft: Any, channel: str, recipient: str | None, email_recipient: str | None = None, whatsapp_recipient: str | None = None) -> dict[str, Any]:
    effective_email_recipient = (email_recipient or recipient or getattr(draft, "approval_email", None) or getattr(draft, "approval_recipient", None))
    effective_whatsapp_recipient = whatsapp_recipient or getattr(draft, "approval_whatsapp", None) or getattr(draft, "approval_recipient", None)

    if channel == "both":
        return {
            "status": "sent",
            "channel": "both",
            "results": [
                send_approval_request(draft, "email", effective_email_recipient),
                send_approval_request(draft, "whatsapp", effective_whatsapp_recipient),
            ],
        }
    if channel in {"in_app", None}:
        return {"status": "skipped", "channel": channel or "in_app"}

    if channel == "whatsapp":
        if not recipient and not effective_whatsapp_recipient:
            raise ValueError("A WhatsApp recipient is required before sending approval requests.")
        final_recipient = recipient or effective_whatsapp_recipient

        account_sid = settings.twilio_account_sid
        auth_token = settings.twilio_auth_token
        from_number = settings.twilio_whatsapp_from

        if not (account_sid and auth_token and from_number):
            raise ValueError("Twilio WhatsApp configuration is missing. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_WHATSAPP_FROM.")

        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
        plain_text, _ = _build_review_message(draft, "pending approval")
        payload = {
            "From": from_number,
            "To": f"whatsapp:{final_recipient}",
            "Body": plain_text,
        }
        response = httpx.post(
            url,
            data=payload,
            auth=(account_sid, auth_token),
            timeout=30,
        )
        response.raise_for_status()
        return {"status": "sent", "channel": "whatsapp", "provider": "twilio", "response": response.json()}

    if channel == "email":
        final_recipient = recipient or effective_email_recipient
        if not final_recipient:
            raise ValueError("An email recipient is required before sending approval requests.")

        if not (settings.smtp_host and settings.smtp_username and settings.smtp_password and settings.email_from):
            raise ValueError("SMTP email configuration is missing. Set SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, and EMAIL_FROM.")

        plain_text, html_body = _build_review_message(draft, "pending approval")
        message = EmailMessage()
        message["Subject"] = f"PostMesh approval request: {draft.platform} draft"
        message["From"] = settings.email_from
        message["To"] = final_recipient
        message.set_content(plain_text)
        message.add_alternative(html_body, subtype="html")
        html_part = message.get_body(preferencelist=("html",))
        media = _media_part(draft)
        if media and html_part is not None:
            cid, data, maintype, subtype = media
            html_part.add_related(data, maintype=maintype, subtype=subtype, cid=f"<{cid}>")

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port or 587) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_username and settings.smtp_password:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)

        return {"status": "sent", "channel": "email", "provider": "smtp", "recipient": final_recipient}

    raise ValueError(f"Unsupported approval channel: {channel}")


def publish_to_platform(draft: Any, job: Any | None = None) -> dict[str, Any]:
    platform = str(draft.platform).lower()
    content = job.content_snapshot if job is not None else getattr(draft, "content", "")

    if not content:
        return {"status": "skipped", "platform": platform, "reason": "empty content"}

    if platform in {"whatsapp", "email"}:
        recipient = getattr(draft, "approval_recipient", None)
        return send_approval_request(
            draft,
            platform,
            recipient,
            email_recipient=getattr(draft, "approval_email", None),
            whatsapp_recipient=getattr(draft, "approval_whatsapp", None),
        )

    provider_urls = {
        "linkedin": settings.linkedin_api_url,
        "x": settings.x_api_url,
        "facebook": settings.facebook_api_url,
        "instagram": settings.instagram_api_url,
        "threads": settings.threads_api_url,
        "youtube": settings.youtube_api_url,
        "reddit": settings.reddit_api_url,
        "blog": settings.blog_api_url,
    }
    provider_url = provider_urls.get(platform)
    access_token = None
    db = SessionLocal()
    try:
        connection = db.query(SocialConnection).filter(
            SocialConnection.provider == platform,
            SocialConnection.status == "connected",
        ).order_by(SocialConnection.created_at.desc()).first()
        if connection:
            provider_url = connection.api_url or provider_url
            if connection.encrypted_access_token and settings.connections_encryption_key:
                access_token = Fernet(settings.connections_encryption_key.encode()).decrypt(
                    connection.encrypted_access_token.encode()
                ).decode()
    finally:
        db.close()

    if platform == "facebook" and connection and connection.account_id and access_token:
        media_url = getattr(draft, "media_url", None)

        if media_url:
            resolved_media_url = media_url
            if resolved_media_url.startswith("/"):
                resolved_media_url = f"http://backend:8000{resolved_media_url}"

            image_response = httpx.get(
                resolved_media_url,
                follow_redirects=True,
                timeout=30,
            )
            image_response.raise_for_status()
            content_type = image_response.headers.get(
                "content-type",
                "image/jpeg",
            ).split(";", 1)[0]

            if not content_type.startswith("image/"):
                raise ValueError("Selected post media is not an image")

            response = httpx.post(
                f"https://graph.facebook.com/v20.0/{connection.account_id}/photos",
                data={"caption": content, "access_token": access_token},
                files={
                    "source": (
                        "postmesh-image",
                        image_response.content,
                        content_type,
                    )
                },
                timeout=60,
            )
        else:
            response = httpx.post(
                f"https://graph.facebook.com/v20.0/{connection.account_id}/feed",
                data={"message": content, "access_token": access_token},
                timeout=30,
            )
        response.raise_for_status()
        payload = response.json()
        return {
            "status": "posted",
            "platform": platform,
            "response": {
                "id": payload.get("id"),
                "url": f"https://www.facebook.com/{payload.get('id', '')}",
            },
        }

    if provider_url:
        headers = {"Authorization": f"Bearer {access_token}"} if access_token else None
        response = httpx.post(
            provider_url,
            json={
                "text": content,
                "platform": platform,
                "draft_id": str(getattr(draft, "id", "")),
                "job_id": str(getattr(job, "id", "")) if job else None,
                "media_url": getattr(draft, "media_url", None),
            },
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        return {"status": "posted", "platform": platform, "response": response.json()}

    if platform in provider_urls:
        return {
            "status": "simulated",
            "platform": platform,
            "message": "Platform adapter is ready; configure its provider endpoint to enable live posting.",
        }

    return {"status": "simulated", "platform": platform, "message": "No live integration configured yet."}
