import base64
import hashlib
import hmac
import json
import secrets
import urllib.parse
import uuid

import httpx
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.models.social_connection import SocialConnection
from app.schemas.social_connection import (
    SocialConnectionCreate,
    SocialConnectionResponse,
)

router = APIRouter(prefix="/api/v1/connections", tags=["Social connections"])
OAUTH_PROVIDERS = {"linkedin", "x", "facebook"}


def _fernet() -> Fernet:
    if not settings.connections_encryption_key:
        raise HTTPException(status_code=503, detail="CONNECTIONS_ENCRYPTION_KEY is not configured")
    try:
        return Fernet(settings.connections_encryption_key.encode())
    except Exception as exc:
        raise HTTPException(status_code=503, detail="CONNECTIONS_ENCRYPTION_KEY is invalid") from exc


def _oauth_settings(provider: str) -> tuple[str | None, str | None, str, str]:
    values = {
        "linkedin": (settings.oauth_linkedin_client_id, settings.oauth_linkedin_client_secret, "https://www.linkedin.com/oauth/v2/authorization", "https://www.linkedin.com/oauth/v2/accessToken"),
        "x": (settings.oauth_x_client_id, settings.oauth_x_client_secret, "https://twitter.com/i/oauth2/authorize", "https://api.twitter.com/2/oauth2/token"),
        "facebook": (settings.oauth_facebook_client_id, settings.oauth_facebook_client_secret, "https://www.facebook.com/v20.0/dialog/oauth", "https://graph.facebook.com/v20.0/oauth/access_token"),
    }
    return values.get(provider, (None, None, "", ""))


def _signed_state(provider: str, code_verifier: str | None = None) -> str:
    nonce = secrets.token_urlsafe(18)
    raw = json.dumps({"provider": provider, "nonce": nonce, "code_verifier": code_verifier})
    signature = hmac.new((settings.connections_encryption_key or "").encode(), raw.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(json.dumps({"value": raw, "signature": signature}).encode()).decode()


@router.get("", response_model=list[SocialConnectionResponse])
def list_connections(db: Session = Depends(get_db)):
    return list(db.scalars(select(SocialConnection).order_by(SocialConnection.created_at.desc())).all())


@router.post("", response_model=SocialConnectionResponse, status_code=status.HTTP_201_CREATED)
def create_connection(payload: SocialConnectionCreate, db: Session = Depends(get_db)):
    if not payload.access_token and not payload.api_url:
        raise HTTPException(status_code=422, detail="Enter an access token or provider endpoint")
    encrypted_token = None
    if payload.access_token:
        encrypted_token = _fernet().encrypt(payload.access_token.encode()).decode()
    connection = SocialConnection(
        provider=payload.provider,
        account_name=payload.account_name.strip(),
        encrypted_access_token=encrypted_token,
        api_url=payload.api_url,
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)
    return connection


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(connection_id: uuid.UUID, db: Session = Depends(get_db)):
    connection = db.get(SocialConnection, connection_id)
    if connection is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    db.delete(connection)
    db.commit()


@router.get("/{provider}/oauth/start")
def start_oauth(provider: str):
    client_id, _, authorization_url, _ = _oauth_settings(provider)
    if not client_id:
        raise HTTPException(status_code=503, detail=f"SSO is not configured for {provider}")
    _fernet()
    redirect_uri = f"{settings.frontend_url}/?oauth_provider={provider}"
    code_verifier = secrets.token_urlsafe(48) if provider == "x" else None
    state = _signed_state(provider, code_verifier)
    query_values = {"client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code", "state": state}
    if provider == "x":
        query_values.update({"scope": "tweet.read users.read offline.access", "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).decode().rstrip("="), "code_challenge_method": "S256"})
    elif provider == "linkedin":
        query_values["scope"] = "openid profile email"
    else:
        query_values["scope"] = "pages_manage_posts,pages_read_user_content"
    query = urllib.parse.urlencode(query_values)
    return {"authorization_url": f"{authorization_url}?{query}"}


@router.get("/{provider}/oauth/callback", response_model=SocialConnectionResponse)
def oauth_callback(provider: str, code: str = Query(...), state: str = Query(...), db: Session = Depends(get_db)):
    client_id, client_secret, _, token_url = _oauth_settings(provider)
    if not client_id or not client_secret or provider not in OAUTH_PROVIDERS:
        raise HTTPException(status_code=503, detail=f"SSO is not configured for {provider}")
    try:
        envelope = json.loads(base64.urlsafe_b64decode(state.encode()).decode())
        expected = hmac.new((settings.connections_encryption_key or "").encode(), envelope["value"].encode(), hashlib.sha256).hexdigest()
        state_value = json.loads(envelope["value"])
        if not hmac.compare_digest(expected, envelope["signature"]) or state_value["provider"] != provider:
            raise ValueError
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid OAuth state") from exc
    token_data = {"code": code, "client_id": client_id, "client_secret": client_secret, "redirect_uri": f"{settings.frontend_url}/?oauth_provider={provider}", "grant_type": "authorization_code"}
    if provider == "x":
        token_data["code_verifier"] = state_value.get("code_verifier") or ""
    response = httpx.post(token_url, data=token_data, timeout=30)
    response.raise_for_status()
    token = response.json().get("access_token")
    if not token:
        raise HTTPException(status_code=502, detail="Provider did not return an access token")
    connection = SocialConnection(provider=provider, account_name=f"{provider.title()} account", encrypted_access_token=_fernet().encrypt(token.encode()).decode())
    db.add(connection)
    db.commit()
    db.refresh(connection)
    return connection