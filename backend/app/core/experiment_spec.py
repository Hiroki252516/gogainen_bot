from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.core.question_sets import LEARNING_CONTENT_VERSION


CURRENT_EXPERIMENT_SPEC_VERSION = 65
CURRENT_PROTOCOL_ID = "experiment-plan-2026-11-27-generated-participant-id-v1"
PREVIOUSLY_ACTIVE_EXPERIMENT_PROTOCOLS = frozenset({
    (
        64,
        "experiment-plan-2026-11-23-participant-code-primary-identifier-presurvey-weekly-frequency-understanding-anchor-v1",
    ),
})
ACTIVE_EXPERIMENT_PROTOCOLS = frozenset({
    (CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID),
    *PREVIOUSLY_ACTIVE_EXPERIMENT_PROTOCOLS,
})
MAX_POST_PRETEST_TESTS = 2
MAX_LEARNING_CONFIRMATION_ATTEMPTS = 1


def is_current_registration(participant: Any) -> bool:
    return (
        participant.experiment_spec_version,
        getattr(participant, "protocol_id", None),
    ) == (CURRENT_EXPERIMENT_SPEC_VERSION, CURRENT_PROTOCOL_ID)


def uses_participant_code_identifier(participant: Any) -> bool:
    return (
        participant.experiment_spec_version,
        getattr(participant, "protocol_id", None),
    ) in PREVIOUSLY_ACTIVE_EXPERIMENT_PROTOCOLS


def participant_code_for_record(participant: Any) -> str | None:
    """Expose the stored code only for records created under the code-ID protocol."""
    return participant.id if uses_participant_code_identifier(participant) else None


def can_resume(participant: Any) -> bool:
    return (
        participant.experiment_spec_version,
        getattr(participant, "protocol_id", None),
    ) in ACTIVE_EXPERIMENT_PROTOCOLS


def assert_current_experiment(participant: Any) -> None:
    if not can_resume(participant):
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "legacy_experiment_read_only",
                "message": "この試用記録は閲覧専用です。新しい実験を開始してください。",
            },
        )
    try:
        if getattr(participant, "learning_content_version", LEARNING_CONTENT_VERSION) != LEARNING_CONTENT_VERSION:
            raise ValueError("learning content version does not match the current experiment")
    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail={"error_code": "learning_content_unavailable", "message": "参加者の教材版に不整合があります。管理者に連絡してください。"},
        ) from exc
