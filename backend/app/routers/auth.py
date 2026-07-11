"""Admin authentication.

Credentials come from the ADMIN_USERNAME / ADMIN_PASSWORD environment
variables (never hardcoded — the repo is public). Successful login returns
a stateless HMAC-signed token with a 12h expiry; the signing key is derived
from the credentials themselves, so no extra secret needs configuring and
changing the password invalidates all outstanding tokens.
"""

import hashlib
import hmac
import os
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])

TOKEN_TTL_SECONDS = 12 * 3600


def _creds() -> tuple[str, str]:
    username = os.getenv("ADMIN_USERNAME")
    password = os.getenv("ADMIN_PASSWORD")
    if not username or not password:
        raise HTTPException(
            status_code=503,
            detail="Admin login not configured: set ADMIN_USERNAME and ADMIN_PASSWORD",
        )
    return username, password


def _signing_key() -> bytes:
    username, password = _creds()
    return hashlib.sha256(f"{username}:{password}".encode()).digest()


def _sign(expiry: int) -> str:
    mac = hmac.new(_signing_key(), str(expiry).encode(), hashlib.sha256).hexdigest()
    return f"{expiry}.{mac}"


def _verify(token: str) -> bool:
    expiry_str, _, mac = token.partition(".")
    if not expiry_str.isdigit() or not mac:
        return False
    if int(expiry_str) < time.time():
        return False
    expected = hmac.new(_signing_key(), expiry_str.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, expected)


_bearer = HTTPBearer(auto_error=False)


def require_admin(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> None:
    if cred is None or not _verify(cred.credentials):
        raise HTTPException(status_code=401, detail="Not authenticated")


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    expires_at: int


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    username, password = _creds()
    ok = hmac.compare_digest(payload.username, username) & hmac.compare_digest(
        payload.password, password
    )
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    expiry = int(time.time()) + TOKEN_TTL_SECONDS
    return LoginResponse(token=_sign(expiry), expires_at=expiry)
