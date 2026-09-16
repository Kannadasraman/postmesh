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
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.auth import get_current_user
from app.db.database import get_db
from app.models.social_connection import SocialConnection
from app.models.user import User
from app.schemas.social_connection import (
    SocialConnectionCreate,
    SocialConnectionResponse,
)

router = APIRouter(prefix="/api/v1/connections", tags=["Social connections"])
OAUTH_PROVIDERS = {"linkedin", "x", "facebook"}


def _oauth_redirect_uri(provider: str) -> str:
    if provider == "linkedin":
        return f"{settings.app_base_url}/api/v1/connections/linkedin/oauth/callback"
    return f"{settings.frontend_url}/?oauth_provider={provider}"


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


def _signed_state(provider: str, user_id: uuid.UUID, code_verifier: str | None = None) -> str:
    nonce = secrets.token_urlsafe(18)
    raw = json.dumps({"provider": provider, "user_id": str(user_id), "nonce": nonce, "code_verifier": code_verifier})
    signature = hmac.new((settings.connections_encryption_key or "").encode(), raw.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(json.dumps({"value": raw, "signature": signature}).encode()).decode()


@router.get("", response_model=list[SocialConnectionResponse])
def list_connections(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return list(db.scalars(select(SocialConnection).where(SocialConnection.user_id == user.id).order_by(SocialConnection.created_at.desc())).all())


@router.post("", response_model=SocialConnectionResponse, status_code=status.HTTP_201_CREATED)
def create_connection(payload: SocialConnectionCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not payload.access_token and not payload.api_url:
        raise HTTPException(status_code=422, detail="Enter an access token or provider endpoint")
    encrypted_token = None
    if payload.access_token:
        encrypted_token = _fernet().encrypt(payload.access_token.encode()).decode()
    connection = SocialConnection(
        user_id=user.id,
        provider=payload.provider,
        account_name=payload.account_name.strip(),
        account_id=payload.account_id.strip() if payload.account_id else None,
        encrypted_access_token=encrypted_token,
        api_url=payload.api_url,
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)
    return connection


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(connection_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    connection = db.scalar(select(SocialConnection).where(SocialConnection.id == connection_id, SocialConnection.user_id == user.id))
    if connection is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    db.delete(connection)
    db.commit()


@router.get("/{provider}/oauth/start")
def start_oauth(provider: str, user: User = Depends(get_current_user)):
    client_id, _, authorization_url, _ = _oauth_settings(provider)
    if not client_id:
        raise HTTPException(status_code=503, detail=f"SSO is not configured for {provider}")
    _fernet()
    redirect_uri = _oauth_redirect_uri(provider)
    code_verifier = secrets.token_urlsafe(48) if provider == "x" else None
    state = _signed_state(provider, user.id, code_verifier)
    query_values = {"client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code", "state": state}
    if provider == "x":
        query_values.update({"scope": "tweet.read users.read offline.access", "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).decode().rstrip("="), "code_challenge_method": "S256"})
    elif provider == "linkedin":
        query_values["scope"] = "openid profile email w_member_social"
    else:
        query_values["scope"] = (
            "pages_show_list,"
            "pages_read_engagement,"
            "pages_manage_posts"
        )
    query = urllib.parse.urlencode(query_values)
    return {"authorization_url": f"{authorization_url}?{query}"}


@router.get("/{provider}/oauth/callback", response_model=SocialConnectionResponse)
def oauth_callback(
    provider: str,
    code: str | None = Query(default=None),
    state: str = Query(...),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if error:
        if provider == "linkedin":
            detail = error_description or error
            return RedirectResponse(
                url=f"{settings.frontend_url}/?oauth_provider=linkedin&oauth_error={urllib.parse.quote(detail)}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        raise HTTPException(status_code=400, detail=error_description or error)
    if not code:
        raise HTTPException(status_code=400, detail="OAuth provider did not return an authorization code")
    client_id, client_secret, _, token_url = _oauth_settings(provider)
    if not client_id or not client_secret or provider not in OAUTH_PROVIDERS:
        raise HTTPException(status_code=503, detail=f"SSO is not configured for {provider}")
    try:
        envelope = json.loads(base64.urlsafe_b64decode(state.encode()).decode())
        expected = hmac.new((settings.connections_encryption_key or "").encode(), envelope["value"].encode(), hashlib.sha256).hexdigest()
        state_value = json.loads(envelope["value"])
        if not hmac.compare_digest(expected, envelope["signature"]) or state_value["provider"] != provider or state_value["user_id"] != str(user.id):
            raise ValueError
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid OAuth state") from exc
    redirect_uri = _oauth_redirect_uri(provider)
    token_data = {"code": code, "client_id": client_id, "client_secret": client_secret, "redirect_uri": redirect_uri, "grant_type": "authorization_code"}
    if provider == "x":
        token_data["code_verifier"] = state_value.get("code_verifier") or ""
    response = httpx.post(token_url, data=token_data, timeout=30)
    response.raise_for_status()
    token = response.json().get("access_token")
    if not token:
        raise HTTPException(status_code=502, detail="Provider did not return an access token")
    account_name = f"{provider.title()} account"
    account_id = None
    if provider == "facebook":
        pages_response = httpx.get(
            "https://graph.facebook.com/v20.0/me/accounts",
            params={"fields": "id,name,access_token", "access_token": token},
            timeout=30,
        )
        pages_response.raise_for_status()
        pages = pages_response.json().get("data", [])
        if not pages:
            raise HTTPException(status_code=403, detail="No Facebook Pages are available for this account")
        page = pages[0]
        token = page.get("access_token") or ""
        account_id = page.get("id")
        account_name = page.get("name") or "Facebook Page"
        if not token or not account_id:
            raise HTTPException(status_code=502, detail="Meta did not return a usable Facebook Page token")
    elif provider == "linkedin":
        profile_response = httpx.get(
            "https://api.linkedin.com/v2/userinfo",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        profile_response.raise_for_status()
        profile = profile_response.json()
        account_id = profile.get("sub")
        account_name = profile.get("name") or profile.get("given_name") or "LinkedIn account"
        if not account_id:
            raise HTTPException(status_code=502, detail="LinkedIn did not return a member ID")
    connection = SocialConnection(user_id=user.id, provider=provider, account_name=account_name, account_id=account_id, encrypted_access_token=_fernet().encrypt(token.encode()).decode())
    db.add(connection)
    db.commit()
    db.refresh(connection)
    if provider == "linkedin":
        return RedirectResponse(
            url=f"{settings.frontend_url}/?oauth_provider=linkedin&connected=1",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return connection
