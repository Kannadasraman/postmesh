import smtplib
from email.message import EmailMessage
from typing import Any

import httpx
from cryptography.fernet import Fernet

from app.core.config import settings
from app.db.database import SessionLocal
from app.models.social_connection import SocialConnection


def _build_review_message(draft: Any, action: str) -> str:
    recipient_label = draft.approval_channel or "in_app"
    lines = [
        f"PostMesh approval update: {action.upper()}",
        "",
        f"Draft ID: {draft.id}",
        f"Platform: {draft.platform}",
        f"Approval channel: {recipient_label}",
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

    return "\n".join(lines)


def send_approval_request(draft: Any, channel: str, recipient: str | None, email_recipient: str | None = None, whatsapp_recipient: str | None = None) -> dict[str, Any]:
    if channel == "both":
        return {
            "status": "sent",
            "channel": "both",
            "results": [
                send_approval_request(draft, "email", email_recipient),
                send_approval_request(draft, "whatsapp", whatsapp_recipient),
            ],
        }
    if channel in {"in_app", None}:
        return {"status": "skipped", "channel": channel or "in_app"}

    if channel == "whatsapp":
        if not recipient:
            raise ValueError("A WhatsApp recipient is required before sending approval requests.")

        account_sid = settings.twilio_account_sid
        auth_token = settings.twilio_auth_token
        from_number = settings.twilio_whatsapp_from

        if not (account_sid and auth_token and from_number):
            raise ValueError("Twilio WhatsApp configuration is missing. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_WHATSAPP_FROM.")

        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
        payload = {
            "From": from_number,
            "To": f"whatsapp:{recipient}",
            "Body": _build_review_message(draft, "pending approval"),
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
        if not recipient:
            raise ValueError("An email recipient is required before sending approval requests.")

        if not (settings.smtp_host and settings.smtp_username and settings.smtp_password and settings.email_from):
            raise ValueError("SMTP email configuration is missing. Set SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, and EMAIL_FROM.")

        message = EmailMessage()
        message["Subject"] = f"PostMesh approval request: {draft.platform} draft"
        message["From"] = settings.email_from
        message["To"] = recipient
        message.set_content(_build_review_message(draft, "pending approval"))

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port or 587) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_username and settings.smtp_password:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)

        return {"status": "sent", "channel": "email", "provider": "smtp", "recipient": recipient}

    raise ValueError(f"Unsupported approval channel: {channel}")


def publish_to_platform(draft: Any, job: Any | None = None) -> dict[str, Any]:
    platform = str(draft.platform).lower()
    content = getattr(draft, "content", "")

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

    if provider_url:
        headers = {"Authorization": f"Bearer {access_token}"} if access_token else None
        response = httpx.post(
            provider_url,
            json={
                "text": content,
                "platform": platform,
                "draft_id": str(getattr(draft, "id", "")),
                "job_id": str(getattr(job, "id", "")) if job else None,
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
