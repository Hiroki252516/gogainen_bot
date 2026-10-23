from __future__ import annotations

from typing import Any

from fastapi import HTTPException


CURRENT_EXPERIMENT_SPEC_VERSION = 5
CURRENT_PROTOCOL_ID = "experiment-plan-2026-10-23-learning-rotation-v1"
MAX_POST_LEARNING_RETEST_CYCLES = 3


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
