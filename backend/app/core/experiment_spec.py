from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.core.question_sets import LEARNING_CONTENT_VERSIONS, question_set_mode


CURRENT_EXPERIMENT_SPEC_VERSION = 13
CURRENT_PROTOCOL_ID = "experiment-plan-2026-10-25-multi-agent-confirmation-v1"
MAX_POST_PRETEST_TESTS = 2


def can_resume(participant: Any) -> bool:
    return (
        participant.experiment_spec_version == CURRENT_EXPERIMENT_SPEC_VERSION
        and getattr(participant, "protocol_id", None) == CURRENT_PROTOCOL_ID
    )


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
        mode = question_set_mode(getattr(participant, "question_set_mode", None))
        if getattr(participant, "learning_content_version", LEARNING_CONTENT_VERSIONS[mode]) != LEARNING_CONTENT_VERSIONS[mode]:
            raise ValueError("learning content version does not match question set")
    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail={"error_code": "question_set_unavailable", "message": "参加者の問題版に不整合があります。管理者に連絡してください。"},
        ) from exc
