"""Azure AD SSO routes — OpenID Connect login via authlib.

Endpoints:
  GET  /auth/sso/login     Redirect to Azure AD login page
  GET  /auth/sso/callback  Handle callback from Azure AD, issue JWT
  GET  /auth/sso/config    Return SSO availability (no auth required)
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import create_access_token, create_refresh_token
from src.core.config import get_settings
from src.db.session import get_db
from src.models.models import AuditLog
from src.services import user_service

logger = logging.getLogger("pbxmonitorx.api.sso")

router = APIRouter(tags=["SSO"])

oauth = OAuth()

# ---------------------------------------------------------------------------
# OAuth provider registration (lazy — only when settings are loaded)
# ---------------------------------------------------------------------------

_provider_registered = False


def _ensure_provider_registered() -> bool:
    """Register the Azure AD OAuth provider if not already done.

    Returns True if SSO is configured and the provider is registered.
    """
    global _provider_registered
    if _provider_registered:
        return True

    settings = get_settings()
    if not settings.azure_ad_enabled or not settings.azure_ad_tenant_id:
        return False

    oauth.register(
        name="azure",
        client_id=settings.azure_ad_client_id,
        client_secret=settings.azure_ad_client_secret,
        server_metadata_url=(
            f"https://login.microsoftonline.com/"
            f"{settings.azure_ad_tenant_id}/v2.0/.well-known/openid-configuration"
        ),
        client_kwargs={
            "scope": "openid email profile User.Read",
        },
    )
    _provider_registered = True
    logger.info("Azure AD OAuth provider registered for tenant %s", settings.azure_ad_tenant_id)
    return True


def _require_sso_configured() -> None:
    """Raise 503 if SSO is not configured."""
    if not _ensure_provider_registered():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Azure AD SSO is not configured",
        )


# ═══════════════════════════════════════════════════════════════════════════
# SSO CONFIG (no auth required)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/auth/sso/config")
async def sso_config():
    """Return whether Azure AD SSO is configured. No authentication required.

    Clients can use this to decide whether to show the SSO login button.
    """
    settings = get_settings()
    enabled = (
        settings.azure_ad_enabled
        and bool(settings.azure_ad_tenant_id)
        and bool(settings.azure_ad_client_id)
    )
    return {
        "sso_enabled": enabled,
        "provider": "azure_ad" if enabled else None,
    }


# ═══════════════════════════════════════════════════════════════════════════
# SSO LOGIN — redirect to Azure AD
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/auth/sso/login")
async def sso_login(request: Request):
    """Initiate Azure AD login. Redirects the browser to Microsoft's login page.

    Generates a random state parameter and stores it in a session cookie
    to protect against CSRF.
    """
    _require_sso_configured()

    settings = get_settings()
    redirect_uri = settings.azure_ad_redirect_uri
    if not redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Azure AD redirect URI is not configured",
        )

    # Generate CSRF state and persist in the session (via Starlette session middleware)
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state

    return await oauth.azure.authorize_redirect(request, redirect_uri, state=state)


# ═══════════════════════════════════════════════════════════════════════════
# SSO CALLBACK — handle Azure AD response, issue JWT
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/auth/sso/callback")
async def sso_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle the callback from Azure AD after user authentication.

    Workflow:
    1. Exchange the authorization code for tokens.
    2. Validate the state parameter against the session.
    3. Extract user info (oid, email, name) from the ID token.
    4. Find or auto-create a local user linked to the Azure OID.
    5. Issue JWT access + refresh tokens in the same format as local login.
    """
    _require_sso_configured()

    # Validate state
    expected_state = request.session.pop("oauth_state", None)
    received_state = request.query_params.get("state")
    if not expected_state or expected_state != received_state:
        logger.warning("SSO callback state mismatch: expected=%s received=%s", expected_state, received_state)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth state — possible CSRF attack",
        )

    # Exchange code for tokens
    try:
        token = await oauth.azure.authorize_access_token(request)
    except OAuthError as e:
        logger.error("Azure AD OAuth error: %s", e.description)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Azure AD authentication failed: {e.description}",
        )

    # Extract user info from the ID token claims
    user_info = token.get("userinfo")
    if not user_info:
        # Fall back to parsing the id_token manually
        id_token = token.get("id_token")
        if not id_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No user info returned from Azure AD",
            )
        user_info = await oauth.azure.parse_id_token(token)

    azure_oid = user_info.get("oid") or user_info.get("sub")
    email = user_info.get("email") or user_info.get("preferred_username", "")
    display_name = user_info.get("name") or user_info.get("given_name", "")

    if not azure_oid:
        logger.error("Azure AD ID token missing 'oid' and 'sub' claims: %s", list(user_info.keys()))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Azure AD token missing required identity claim",
        )

    # Find or create user
    settings = get_settings()
    if not settings.azure_ad_auto_create_users:
        # Check if user already exists before creating
        from sqlalchemy import select
        from src.models.models import AppUser
        result = await db.execute(
            select(AppUser).where(AppUser.azure_oid == azure_oid)
        )
        existing = result.scalar_one_or_none()
        if not existing:
            # Also check by email
            if email:
                result = await db.execute(
                    select(AppUser).where(AppUser.email == email)
                )
                existing = result.scalar_one_or_none()
            if not existing:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Auto-creation of SSO users is disabled. Contact an administrator.",
                )

    user = await user_service.find_or_create_sso_user(
        db=db,
        azure_oid=azure_oid,
        email=email,
        display_name=display_name,
    )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled. Contact an administrator.",
        )

    # Audit log the SSO login
    ip = request.client.host if request.client else None
    db.add(AuditLog(
        user_id=user.id,
        username=user.username,
        action="user_sso_login",
        target_type="user",
        target_name=user.username,
        detail={
            "azure_oid": azure_oid,
            "email": email,
            "ip": ip,
        },
        success=True,
        ip_address=ip,
    ))
    await db.flush()

    # Issue JWT tokens — same format as local login
    access_token, expires = create_access_token(
        str(user.id), user.username, user.role,
    )
    refresh_token = create_refresh_token(str(user.id))

    logger.info("SSO login successful for user '%s' (oid=%s)", user.username, azure_oid)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_at": expires.isoformat(),
        "user": {
            "id": str(user.id),
            "username": user.username,
            "role": user.role,
            "display_name": user.display_name,
            "email": user.email,
            "auth_method": user.auth_method,
        },
    }
