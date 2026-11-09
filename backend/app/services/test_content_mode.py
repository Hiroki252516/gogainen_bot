"""New-participant question content mode settings."""

from __future__ import annotations

from typing import Any

from app.core.question_sets import ASSESSMENT_MODE_LABELS
from app.models import RuntimeSetting

APPLICATION = "application"
BASIC_UNDERSTANDING = "basic_understanding"
FOUR_TOPIC_FUNDAMENTALS = "four_topic_fundamentals"
DEFAULT_MODE = FOUR_TOPIC_FUNDAMENTALS


def normalize_mode(value: str | None) -> str:
    if value in ASSESSMENT_MODE_LABELS:
        return value
    if value is None:
        return DEFAULT_MODE
    raise ValueError("unsupported test content mode")


def current_mode(db: Any) -> str:
    setting = db.get(RuntimeSetting, 1)
    return normalize_mode(setting.test_content_mode if setting else None)


def save_mode(db: Any, mode: str) -> str:
    mode = normalize_mode(mode)
    setting = db.get(RuntimeSetting, 1)
    if setting is None:
        setting = RuntimeSetting(id=1, test_content_mode=mode)
        db.add(setting)
    else:
        setting.test_content_mode = mode
    db.commit()
    return mode


def participant_mode(participant: object) -> str:
    value = getattr(participant, "test_content_mode", None)
    if value is not None:
        return normalize_mode(value)
    # Old records have no mode snapshot and must continue using the original bank.
    return APPLICATION


def mode_label(value: str | None) -> str | None:
    return ASSESSMENT_MODE_LABELS.get(value) if value is not None else None
