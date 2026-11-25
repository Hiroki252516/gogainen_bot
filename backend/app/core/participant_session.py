from __future__ import annotations

import base64
import hashlib
import hmac
import time

from fastapi import HTTPException, Request, Response

from app.core.config import get_settings

PARTICIPANT_SESSION_COOKIE = "participant_session"
PARTICIPANT_SESSION_TTL_SECONDS = 24 * 60 * 60


def _secret() -> bytes:
    value = get_settings().participant_session_secret.get_secret_value()
    if len(value) < 32:
        raise RuntimeError("PARTICIPANT_SESSION_SECRET must be a stable value of at least 32 characters")
    return value.encode("utf-8")


def validate_participant_session_secret() -> None:
    _secret()


def _signature(participant_id: str, expires_at: int) -> str:
    message = f"{participant_id}.{expires_at}".encode("utf-8")
    digest = hmac.new(_secret(), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def issue_participant_session(response: Response, participant_id: str) -> None:
    expires_at = int(time.time()) + PARTICIPANT_SESSION_TTL_SECONDS
    token = f"{expires_at}.{_signature(participant_id, expires_at)}"
    secure = get_settings().app_env.lower() in {"production", "prod"}
    response.set_cookie(
        key=PARTICIPANT_SESSION_COOKIE,
        value=token,
        max_age=PARTICIPANT_SESSION_TTL_SECONDS,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/api",
    )


def participant_session_matches(request: Request, participant_id: str) -> bool:
    token = request.cookies.get(PARTICIPANT_SESSION_COOKIE, "")
    try:
        expiry_text, signature = token.split(".", 1)
        expires_at = int(expiry_text)
    except (ValueError, TypeError):
        return False
    current_time = int(time.time())
    if expires_at < current_time or expires_at > current_time + PARTICIPANT_SESSION_TTL_SECONDS:
        return False
    expected = _signature(participant_id, expires_at)
    return hmac.compare_digest(signature, expected)


def require_participant_session(request: Request, participant_id: str) -> None:
    if not participant_session_matches(request, participant_id):
        raise HTTPException(status_code=401, detail="参加者セッションが無効または期限切れです。")
