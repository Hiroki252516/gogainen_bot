from sqlalchemy.orm import Session

from app.core.question_sets import STANDARD, question_set_mode
from app.models import RuntimeSetting


def current_question_set_mode(db: Session) -> str:
    row = db.get(RuntimeSetting, 1)
    return question_set_mode(row.question_set_mode if row else None)


def save_question_set_mode(db: Session, mode: str) -> str:
    mode = question_set_mode(mode)
    row = db.get(RuntimeSetting, 1)
    if row is None:
        row = RuntimeSetting(id=1, option_order_mode="debug_fixed", question_set_mode=STANDARD)
        db.add(row)
    row.question_set_mode = mode
    db.commit()
    return mode
