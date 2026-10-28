"""Local researcher login, independent of the Codex account and study records."""

import secrets
import time
from threading import Lock

from fastapi import HTTPException, Request, Response

from app.core.config import get_settings


COOKIE_NAME = "tutor_admin_session"
SESSION_SECONDS = 30 * 60
_sessions: dict[str, float] = {}
_lock = Lock()
_LOGIN_PATH = "/api/admin/auth/login"
_LOGOUT_PATH = "/api/admin/auth/logout"


def _is_admin_path(path: str) -> bool:
    return (
        path == "/api/admin"
        or path.startswith("/api/admin/")
        or path == "/api/seed"
        or (path.startswith("/api/participants/") and path.endswith("/evaluation-summary/recalculate"))
    )


def require_admin(request: Request) -> None:
    path = request.url.path.rstrip("/")
    if request.method == "OPTIONS" or not _is_admin_path(path):
        return
    # Cookie-based writes must originate from the configured UI or the API itself.
    if request.method not in {"GET", "HEAD"}:
        origin = request.headers.get("origin")
        allowed = {get_settings().frontend_origin.rstrip("/"), "http://127.0.0.1:3000", str(request.base_url).rstrip("/")}
        if origin and origin not in allowed:
            raise HTTPException(status_code=403, detail="この接続元から管理操作はできません。")
    if path in {_LOGIN_PATH, _LOGOUT_PATH} and request.method == "POST":
        return
    token = request.cookies.get(COOKIE_NAME, "")
    with _lock:
        expires = _sessions.get(token, 0)
        if expires <= time.monotonic():
            _sessions.pop(token, None)
            raise HTTPException(status_code=401, detail="管理画面のパスワードを入力してください。")


def login(password: str, request: Request, response: Response) -> None:
    expected = get_settings().admin_password.get_secret_value()
    if not expected or not secrets.compare_digest(password.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(status_code=401, detail="パスワードが違います。")
    now = time.monotonic()
    token = secrets.token_urlsafe(32)
    with _lock:
        for old_token, expiry in list(_sessions.items()):
            if expiry <= now:
                del _sessions[old_token]
        _sessions.pop(request.cookies.get(COOKIE_NAME, ""), None)
        _sessions[token] = now + SESSION_SECONDS
    response.set_cookie(
        COOKIE_NAME, token, path="/api", httponly=True, samesite="strict",
        secure=request.url.scheme == "https", max_age=SESSION_SECONDS,
    )


def logout(request: Request, response: Response) -> None:
    with _lock:
        _sessions.pop(request.cookies.get(COOKIE_NAME, ""), None)
    response.delete_cookie(
        COOKIE_NAME, path="/api", httponly=True, samesite="strict",
        secure=request.url.scheme == "https",
    )
