"""Persist the Q1-only switch and read each participant's registration snapshot."""
from app.models import RuntimeSetting


def enabled(participant) -> bool:
    return getattr(participant, "first_question_only", None) is True


def question_numbers(participant) -> tuple[int, ...]:
    return (1,) if enabled(participant) else (1, 2)


def current_setting(db) -> bool:
    row = db.get(RuntimeSetting, 1)
    return row.first_question_only is True if row else False


def save_setting(db, value: bool) -> bool:
    row = db.get(RuntimeSetting, 1)
    if row is None:
        row = RuntimeSetting(id=1)
        db.add(row)
    row.first_question_only = value
    db.commit()
    return value
