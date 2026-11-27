from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from datetime import timedelta

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.experiment_spec import CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID, can_resume
from app.db.session import get_db
from app.models import Participant, ParticipantSession, now


SESSION_SECONDS = 24 * 60 * 60
_UNAUTHORIZED = "参加者セッションを確認できません。同意画面から実験を開始してください。"


def _secret() -> bytes:
    value = get_settings().participant_session_secret.get_secret_value()
    if len(value.encode("utf-8")) < 32:
        raise HTTPException(status_code=503, detail="参加者セッションのサーバー設定を確認してください。")
    return value.encode("utf-8")


def validate_session_configuration() -> None:
    _secret()


def _cookie_name(participant_id: str, secret: bytes) -> str:
    digest = hmac.new(secret, b"participant-cookie:" + participant_id.encode("ascii"), hashlib.sha256).hexdigest()
    return f"tutor_participant_{digest[:32]}"


def _token_signature(payload: str, secret: bytes) -> str:
    return hmac.new(secret, payload.encode("ascii"), hashlib.sha256).hexdigest()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def issue_participant_session(
    db: Session,
    response: Response,
    request: Request,
    participant_id: str,
) -> None:
    secret = _secret()
    participant = db.get(Participant, participant_id)
    if participant is None or participant.experiment_spec_version != CURRENT_EXPERIMENT_SPEC_VERSION or participant.protocol_id != CURRENT_PROTOCOL_ID:
        raise HTTPException(status_code=409, detail="参加者登録を確認できません。")

    expires_unix = int(time.time()) + SESSION_SECONDS
    payload = f"v1.{secrets.token_urlsafe(32)}.{expires_unix}"
    token = f"{payload}.{_token_signature(payload, secret)}"
    expires_at = now() + timedelta(seconds=SESSION_SECONDS)
    db.query(ParticipantSession).filter(ParticipantSession.expires_at <= now()).delete(synchronize_session=False)
    db.add(ParticipantSession(
        token_hash=_token_hash(token),
        participant_id=participant_id,
        expires_at=expires_at,
    ))
    db.commit()
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
    response.set_cookie(
        _cookie_name(participant_id, secret),
        token,
        max_age=SESSION_SECONDS,
        path="/api",
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https" or forwarded_proto == "https",
    )


async def _participant_id_from_request(request: Request, db: Session) -> str | None:
    for name in ("participant_id", "participant_code"):
        value = request.path_params.get(name)
        if isinstance(value, str):
            return value

    path = request.url.path
    if request.method not in {"GET", "HEAD", "OPTIONS"} and path in {
        "/api/attempts",
        "/api/attempts/term-page",
        "/api/tutor-sessions",
    }:
        try:
            payload = await request.json()
            if isinstance(payload, dict):
                value = payload.get("participant_id") or payload.get("participant_code")
                if isinstance(value, str):
                    return value
        except Exception:
            return None

    session_id = request.path_params.get("session_id")
    if session_id:
        from app.models import TutorSession

        session = db.get(TutorSession, session_id)
        return session.participant_id if session else None
    turn_id = request.path_params.get("turn_id")
    if turn_id:
        from app.models import TutorSession, TutorTurn

        turn = db.get(TutorTurn, turn_id)
        session = db.get(TutorSession, turn.tutor_session_id) if turn else None
        return session.participant_id if session else None
    return None


async def require_participant_session(request: Request, db: Session = Depends(get_db)) -> None:
    path = request.url.path.rstrip("/")
    if request.method == "OPTIONS" or path in {"/api/health", "/api/seed", "/api/participants", "/api/registrations"}:
        return
    if path.startswith("/api/admin/"):
        return

    participant_id = await _participant_id_from_request(request, db)
    if not participant_id:
        return
    participant = db.get(Participant, participant_id)
    if participant is None:
        return
    if not can_resume(participant):
        return

    secret = _secret()
    if request.method not in {"GET", "HEAD"}:
        origin = request.headers.get("origin")
        allowed_origins = {
            get_settings().frontend_origin.rstrip("/"),
            "http://127.0.0.1:3000",
            str(request.base_url).rstrip("/"),
        }
        if origin and origin.rstrip("/") not in allowed_origins:
            raise HTTPException(status_code=403, detail="この接続元から参加者操作はできません。")

    name = _cookie_name(participant_id, secret)
    token = request.cookies.get(name, "")
    try:
        version, nonce, expires_text, signature = token.split(".")
        payload = f"{version}.{nonce}.{expires_text}"
        expires_unix = int(expires_text)
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail=_UNAUTHORIZED)
    if (
        version != "v1"
        or expires_unix <= int(time.time())
        or not hmac.compare_digest(signature, _token_signature(payload, secret))
    ):
        raise HTTPException(status_code=401, detail=_UNAUTHORIZED)

    session = db.get(ParticipantSession, _token_hash(token))
    if (
        session is None
        or session.participant_id != participant_id
        or session.expires_at <= now()
    ):
        raise HTTPException(status_code=401, detail=_UNAUTHORIZED)
