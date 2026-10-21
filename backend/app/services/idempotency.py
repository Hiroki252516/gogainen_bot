from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.experiment_spec import assert_current_experiment
from app.models import IdempotencyRecord, Participant, now


IDEMPOTENCY_KEY_MAX_LENGTH = 128
IDEMPOTENCY_LEASE_MINUTES = 15


@dataclass(frozen=True)
class Reservation:
    record_id: str
    owner_token: str


def normalize_idempotency_key(value: str | None) -> str | None:
    if value is None:
        return None
    key = value.strip()
    if not key:
        return None
    if len(key) > IDEMPOTENCY_KEY_MAX_LENGTH:
        raise HTTPException(status_code=400, detail="Idempotency-Keyは128文字以内で指定してください。")
    return key


def request_fingerprint(value: Any) -> str:
    normalized = _json_safe(value)
    encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def idempotency_error(code: str, message: str, **extra: Any) -> HTTPException:
    detail: dict[str, Any] = {"error_code": code, "message": message}
    detail.update(extra)
    return HTTPException(status_code=409, detail=detail)


async def run_idempotent(
    db: Session,
    *,
    scope: str,
    key: str | None,
    participant_id: str | None,
    request_data: Any,
    operation: Callable[[], Any | Awaitable[Any]],
) -> Any:
    """Run a participant mutation once and replay its stored result on retries.

    The reservation is committed before the business operation so concurrent
    requests can observe the in-progress state. The business changes and the
    completed record are committed together at the end of the operation.
    """
    _assert_current_participant(db, participant_id)
    normalized_key = normalize_idempotency_key(key)
    if normalized_key is None:
        return await _call(operation)

    fingerprint = request_fingerprint(request_data)
    reservation = _reserve(db, scope, normalized_key, fingerprint, participant_id)
    if isinstance(reservation, tuple):
        return reservation[0]

    previous_defer_commit = db.info.get("defer_commits", False)
    db.info["defer_commits"] = True
    try:
        result = await _call(operation)
        record = db.get(IdempotencyRecord, reservation.record_id)
        if record is None or record.owner_token != reservation.owner_token:
            raise RuntimeError("idempotency reservation ownership was lost")
        if participant_id is not None:
            # Synchronize final writes with withdrawal, including deferred AI logs.
            if db.query(Participant.id).filter_by(id=participant_id).with_for_update().first() is None:
                raise HTTPException(404, "被験者が見つかりません。")
        _attach_deferred_ai_logs(db)
        record.status = "completed"
        record.response_status = 200
        record.response_json = _json_safe(result)
        if record.participant_id is None and isinstance(result, dict) and result.get("participant_id"):
            record.participant_id = str(result["participant_id"])
        record.updated_at = now()
        record.completed_at = record.updated_at
        record.lease_expires_at = None
        db.commit()
        db.info.pop("deferred_ai_logs", None)
        return result
    except HTTPException as exc:
        db.rollback()
        _store_failure(db, reservation, exc.status_code, exc.detail)
        raise
    except Exception:
        db.rollback()
        _store_failure(
            db,
            reservation,
            500,
            {"error_code": "idempotency_operation_failed", "message": "処理に失敗しました。もう一度お試しください。"},
        )
        raise
    finally:
        db.info["defer_commits"] = previous_defer_commit
        db.info.pop("deferred_ai_logs", None)


async def _call(operation: Callable[[], Any | Awaitable[Any]]) -> Any:
    result = operation()
    if inspect.isawaitable(result):
        return await result
    return result


def _reserve(
    db: Session,
    scope: str,
    key: str,
    fingerprint: str,
    participant_id: str | None,
) -> Reservation | tuple[Any]:
    existing = db.query(IdempotencyRecord).filter_by(scope=scope, idempotency_key=key).one_or_none()
    if existing:
        _assert_current_participant(db, existing.participant_id)
        if existing.request_hash != fingerprint:
            raise idempotency_error(
                "idempotency_key_conflict",
                "同じIdempotency-Keyで別の内容が送信されました。元の処理結果を維持します。",
            )
        if existing.status == "completed":
            return _replay(existing)
        if existing.status == "failed" and (existing.response_status or 500) < 500:
            return _replay(existing)
        if existing.status == "in_progress" and existing.lease_expires_at and existing.lease_expires_at > now():
            raise idempotency_error(
                "idempotency_in_progress",
                "同じ操作を処理中です。しばらく待ってから同じ内容を再送してください。",
            )

        existing.status = "in_progress"
        existing.owner_token = str(uuid4())
        existing.updated_at = now()
        existing.lease_expires_at = existing.updated_at + timedelta(minutes=IDEMPOTENCY_LEASE_MINUTES)
        existing.response_status = None
        existing.response_json = None
        db.commit()
        return Reservation(existing.id, existing.owner_token)

    record = IdempotencyRecord(
        scope=scope,
        idempotency_key=key,
        participant_id=participant_id,
        request_hash=fingerprint,
        status="in_progress",
        owner_token=str(uuid4()),
        lease_expires_at=now() + timedelta(minutes=IDEMPOTENCY_LEASE_MINUTES),
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(IdempotencyRecord).filter_by(scope=scope, idempotency_key=key).one_or_none()
        if existing is None:
            raise
        _assert_current_participant(db, existing.participant_id)
        if existing.request_hash != fingerprint:
            raise idempotency_error(
                "idempotency_key_conflict",
                "同じIdempotency-Keyで別の内容が送信されました。元の処理結果を維持します。",
            )
        if existing.status == "completed" or (existing.status == "failed" and (existing.response_status or 500) < 500):
            return _replay(existing)
        raise idempotency_error(
            "idempotency_in_progress",
            "同じ操作を処理中です。しばらく待ってから同じ内容を再送してください。",
        )
    return Reservation(record.id, record.owner_token)


def _replay(record: IdempotencyRecord) -> tuple[Any]:
    status = record.response_status or 500
    body = record.response_json or {}
    if status >= 400:
        detail = body.get("detail", body) if isinstance(body, dict) else body
        raise HTTPException(status_code=status, detail=detail)
    return (body,)


def _assert_current_participant(db: Session, participant_id: str | None) -> None:
    if participant_id is None:
        return
    participant = db.get(Participant, participant_id)
    if participant is None:
        raise HTTPException(status_code=404, detail="被験者が見つかりません。")
    assert_current_experiment(participant)


def _store_failure(db: Session, reservation: Reservation, status: int, detail: Any) -> None:
    record = db.get(IdempotencyRecord, reservation.record_id)
    if record is None or record.owner_token != reservation.owner_token:
        return
    _attach_deferred_ai_logs(db)
    record.status = "failed"
    record.response_status = status
    record.response_json = {"detail": _json_safe(detail)}
    record.updated_at = now()
    record.completed_at = record.updated_at
    record.lease_expires_at = None
    db.commit()
    db.info.pop("deferred_ai_logs", None)


def _attach_deferred_ai_logs(db: Session) -> None:
    """Attach AI logs to the same final transaction as the idempotency result."""
    for log in db.info.get("deferred_ai_logs", []):
        db.add(log)


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
