from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.question_sets import EASY, STANDARD, question_set_mode


def current_question_set_mode(db: Session) -> str:
    return STANDARD


def save_question_set_mode(db: Session, mode: str) -> str:
    mode = question_set_mode(mode)
    if mode == EASY:
        raise HTTPException(
            status_code=422,
            detail={"error_code": "question_set_retired", "message": "易しい版の新規登録は停止しています。"},
        )
    return STANDARD


def require_aggregate_question_set_mode(mode: str | None) -> str:
    try:
        mode = question_set_mode(mode)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="unsupported question set mode") from exc
    if mode == EASY:
        raise HTTPException(
            status_code=422,
            detail={"error_code": "question_set_aggregation_retired", "message": "易しい版の群集計は停止しています。"},
        )
    return STANDARD
