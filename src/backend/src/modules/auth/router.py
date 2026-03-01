"""Authentication endpoints — local user auth with JWT."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    """Authenticate app user and return JWT tokens."""
    # TODO: Verify credentials against app_user table (bcrypt)
    # TODO: Check lockout (failed_logins, locked_until)
    # TODO: Generate JWT access + refresh tokens
    # TODO: Audit log entry
    raise HTTPException(status_code=501, detail="Not yet implemented")


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token():
    """Refresh an expired access token using a valid refresh token."""
    raise HTTPException(status_code=501, detail="Not yet implemented")


@router.post("/logout")
async def logout():
    """Invalidate the current session."""
    # TODO: Add token to blacklist in Redis
    return {"message": "Logged out"}
