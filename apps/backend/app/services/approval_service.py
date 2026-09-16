import base64
import hashlib
import hmac
import json
import time
from typing import Any

from app.core.config import settings


def _approval_secret() -> str:
    return settings.email_approval_secret or "postmesh-dev-secret"


def _b64_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def create_approval_token(draft_id: str, action: str, scope: str = "draft") -> str:
    payload = {
        "draft_id": draft_id,
        "action": action,
        "scope": scope,
        "exp": int(time.time()) + 60 * 60 * 24 * 7,
    }
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()).decode().rstrip("=")
    signature = hmac.new(_approval_secret().encode(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{signature}"


def decode_approval_token(token: str) -> dict[str, Any]:
    if not token:
        raise ValueError("Approval token is required")

    try:
        raw, signature = token.split(".", 1)
    except ValueError as exc:  # pragma: no cover - malformed token
        raise ValueError("Malformed approval token") from exc

    payload_bytes = _b64_decode(raw)
    expected = hmac.new(_approval_secret().encode(), raw.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise ValueError("Approval token signature is invalid")

    payload = json.loads(payload_bytes.decode())
    if payload.get("exp", 0) < int(time.time()):
        raise ValueError("Approval token has expired")

    return payload
