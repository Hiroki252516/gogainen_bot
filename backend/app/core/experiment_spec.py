from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.core.question_sets import LEARNING_CONTENT_VERSION


CURRENT_EXPERIMENT_SPEC_VERSION = 48
CURRENT_PROTOCOL_ID = "experiment-plan-2026-11-10-presurvey-exposure-understanding-split-v1"
MAX_POST_PRETEST_TESTS = 2
MAX_LEARNING_CONFIRMATION_ATTEMPTS = 1


def can_resume(participant: Any) -> bool:
    if (
        participant.experiment_spec_version != CURRENT_EXPERIMENT_SPEC_VERSION
        or getattr(participant, "protocol_id", None) != CURRENT_PROTOCOL_ID
    ):
        return False
    return True


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
