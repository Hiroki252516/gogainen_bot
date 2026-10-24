from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.ai.interaction_history import project_interaction_history
from app.core.experiment_spec import assert_current_experiment
from app.core.question_sets import question_set_mode
from app.models import Attempt, Participant, Question, QuestionOption, Term, TutorSession, TutorTurn
from app.seed.content_loader import learning_question_spec
from app.services.option_order import assessment_bank_index, present_options


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _selected_snapshot_options(snapshot: list | None, selected_ids: list[str]) -> list[dict[str, str]]:
    by_id = {row.get("option_id"): row for row in snapshot or [] if isinstance(row, dict)}
    return [{"label": by_id[option_id].get("label") or by_id[option_id].get("option_label"), "body": by_id[option_id]["body"]} for option_id in selected_ids]


def _test_record(db: Session, attempt: Attempt) -> dict[str, Any]:
    selected_ids = attempt.selected_option_ids or []
    snapshot = [row for row in attempt.option_order_snapshot or [] if isinstance(row, dict) and row.get("body") and (row.get("label") or row.get("option_label"))]
    existing = {row.get("option_id") for row in snapshot if isinstance(row, dict)}
    missing_ids = [option_id for option_id in selected_ids if option_id not in existing]
    if missing_ids:
        saved_question = db.get(Question, attempt.question_id)
        term = db.get(Term, attempt.term_id)
        participant = db.get(Participant, attempt.participant_id)
        options = db.query(QuestionOption).filter(QuestionOption.question_id == attempt.question_id, QuestionOption.option_label.in_(list("ABCDEFGHIJ"))).all()
        displayed = present_options(options, mode=participant.option_order_mode, bank="assessment", item_index=assessment_bank_index(term.slug, attempt.phase, saved_question.variant_key))
        snapshot.extend(row for row in displayed if row["option_id"] in missing_ids)
    question = db.get(Question, attempt.question_id) if not attempt.question_body_snapshot else None
    return {
        "source_type": "test_attempt", "phase": attempt.phase, "test_round": attempt.test_round,
        "session_index": None, "turn_index": None,
        "question_body": attempt.question_body_snapshot or (question.body if question else ""),
        "selected_options": _selected_snapshot_options(snapshot, selected_ids),
        "is_correct": attempt.is_correct, "question_shown_at": _iso(attempt.question_shown_at),
        "answered_at": _iso(attempt.answered_at), "response_time_sec": attempt.response_time_sec,
    }


def _learning_record(db: Session, session: TutorSession, turn: TutorTurn, projected: dict[str, Any] | None = None) -> dict[str, Any]:
    grading = projected["grading_json"] if projected else (turn.grading_json or {})
    timing = (projected or {}).get("timing") or {}
    question = turn.practice_question_json or {}
    snapshot = [row for row in question.get("options") or [] if isinstance(row, dict) and row.get("body") and row.get("label")]
    selected_ids = grading.get("selected_option_ids") or []
    available = {row.get("option_id") for row in snapshot if isinstance(row, dict)}
    if not question.get("body") or not set(selected_ids).issubset(available):
        term = db.get(Term, session.term_id)
        stage = grading.get("learning_stage") or (question.get("stage_meta") or {}).get("learning_stage") or "conceptual_change"
        participant = db.get(Participant, session.participant_id)
        restored = learning_question_spec(term.slug, stage, int(question.get("learning_variant_index") or 1), question_set_mode(participant.question_set_mode))
        snapshot = [*snapshot, *[row for row in restored["options"] if row["option_id"] not in available]]
        body = question.get("body") or turn.learner_prompt or restored["body"]
    else:
        body = question["body"]
    return {
        "source_type": "learning_turn", "phase": "learning", "test_round": None,
        "session_index": session.session_index, "turn_index": turn.turn_index,
        "question_body": body, "selected_options": _selected_snapshot_options(snapshot, selected_ids),
        "is_correct": grading["is_sufficient"],
        "question_shown_at": _iso(timing.get("question_shown_at") if projected else turn.question_shown_at),
        "answered_at": _iso(timing.get("answered_at") if projected else turn.answered_at),
        "response_time_sec": timing.get("response_time_sec") if projected else turn.response_time_sec,
    }


def build_interaction_history(db: Session, participant_id: str, term_id: str, *, projected_answer: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Merge graded observations for one term, including a not-yet-committed next-turn projection."""
    assert_current_experiment(db.get(Participant, participant_id))
    ordered: list[tuple[datetime, str, str, dict[str, Any]]] = []
    attempts = db.query(Attempt).filter(
        Attempt.participant_id == participant_id, Attempt.term_id == term_id,
        Attempt.phase.in_(("pretest", "retest", "final_test")), Attempt.is_correct.is_not(None),
    ).all()
    for attempt in attempts:
        ordered.append((attempt.answered_at or attempt.created_at, "test_attempt", attempt.id, _test_record(db, attempt)))
    sessions = db.query(TutorSession).filter_by(participant_id=participant_id, term_id=term_id).all()
    session_by_id = {session.id: session for session in sessions}
    projected_turn = projected_answer.get("turn") if projected_answer else None
    turns = db.query(TutorTurn).filter(
        TutorTurn.tutor_session_id.in_(list(session_by_id)), TutorTurn.learner_response.is_not(None),
    ).all() if sessions else []
    for turn in turns:
        if projected_turn and turn.id == projected_turn.id:
            continue
        if not isinstance((turn.grading_json or {}).get("is_sufficient"), bool):
            continue
        ordered.append((turn.answered_at or turn.created_at, "learning_turn", turn.id, _learning_record(db, session_by_id[turn.tutor_session_id], turn)))
    if projected_turn is not None:
        session = session_by_id[projected_turn.tutor_session_id]
        answered_at = (projected_answer.get("timing") or {}).get("answered_at")
        ordered.append((answered_at or projected_turn.created_at, "learning_turn", projected_turn.id, _learning_record(db, session, projected_turn, projected_answer)))
    ordered.sort(key=lambda row: row[:3])
    return project_interaction_history([row[3] for row in ordered])
