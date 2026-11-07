"""Persist the Q1-only switch and read each participant's registration snapshot."""
from fastapi import HTTPException

from app.models import RuntimeSetting


def enabled(participant) -> bool:
    return getattr(participant, "first_question_only", None) is True


def question_numbers(participant) -> tuple[int, ...]:
    return (1,) if enabled(participant) else (1, 2)


def current_setting(db) -> bool:
    # V6 contains only question 1; the current cohort cannot disable this condition.
    return True


def save_setting(db, value: bool) -> bool:
    if value is not True:
        raise HTTPException(status_code=409, detail="V6では設問1のみを出題します。")
    row = db.get(RuntimeSetting, 1)
    if row is None:
        row = RuntimeSetting(id=1)
        db.add(row)
    row.first_question_only = True
    db.commit()
    return True
