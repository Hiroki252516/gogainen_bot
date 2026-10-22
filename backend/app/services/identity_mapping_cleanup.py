"""Recoverable cleanup for identity mappings after research-record deletion."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditEvent
from app.services import identity_mapping

logger = logging.getLogger(__name__)

PENDING = "pending"
COMPLETE = "complete"


def _status_expression():
    return AuditEvent.after_json["identity_mapping_cleanup"].as_string()


def participant_deletion_event(db: Session, participant_id: str) -> AuditEvent | None:
    """Return this participant's latest deletion event when it has cleanup state."""
    return (
        db.query(AuditEvent)
        .filter(
            AuditEvent.action == "delete_participant",
            AuditEvent.entity_type == "participant",
            AuditEvent.entity_id == participant_id,
            _status_expression().in_((PENDING, COMPLETE)),
        )
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .first()
    )


def deletion_response(event: AuditEvent) -> dict[str, Any]:
    before = event.before_json or {}
    return {
        "participant_id": event.entity_id,
        "deleted": True,
        "deleted_counts": before.get("deleted_counts", {}),
    }


def complete_identity_mapping_cleanup(db: Session, event: AuditEvent) -> bool:
    """Delete the external mapping, then durably mark its outbox event complete.

    Repeating either step is safe: mapping deletion is idempotent, and a failed
    research-DB status commit leaves the event pending for another attempt.
    """
    if (event.after_json or {}).get("identity_mapping_cleanup") != PENDING:
        return (event.after_json or {}).get("identity_mapping_cleanup") == COMPLETE
    if not event.entity_id:
        logger.error("Pending identity mapping cleanup has no participant ID")
        return False

    try:
        identity_mapping.delete_mapping(event.entity_id)
    except Exception:
        db.rollback()
        logger.exception("Identity mapping cleanup failed for a deleted participant")
        return False

    event.after_json = {**(event.after_json or {}), "identity_mapping_cleanup": COMPLETE}
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not mark identity mapping cleanup complete")
        return False
    return True


def recover_pending_identity_mapping_cleanups(db: Session) -> int:
    """Retry all durable cleanup events; return the number still pending."""
    pending_ids = [
        event.id
        for event in db.query(AuditEvent.id)
        .filter(
            AuditEvent.action == "delete_participant",
            AuditEvent.entity_type == "participant",
            _status_expression() == PENDING,
        )
        .all()
    ]
    failed = 0
    for event_id in pending_ids:
        event = db.get(AuditEvent, event_id)
        if event is not None and not complete_identity_mapping_cleanup(db, event):
            failed += 1
    return failed
