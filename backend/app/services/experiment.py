from __future__ import annotations

import csv
import json
import random
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ai.codex_app_server_backend import CodexAppServerError
from app.ai.backend import lower_level, normalize_level, raise_level, strategy_for
from app.ai.factory import get_ai_backend
from app.core.config import get_settings
from app.rag.retriever import retrieve_rag_context
from app.models import (
    AICallLog,
    Attempt,
    EvaluationSummary,
    ExportJob,
    LearnerState,
    Participant,
    Question,
    QuestionDisplayOrder,
    QuestionOption,
    RecurrenceEvent,
    Term,
    TermAssignment,
    TutorSession,
    TutorTurn,
    now,
)


PUBLIC_LEVEL = {"L3": "用語理解から確認", "L2": "概念理解を確認"}
PRETEST_TERM_ORDER = {"transfer_learning": 0, "llm_training_process": 1}
PRETEST_TERM_SLUGS = set(PRETEST_TERM_ORDER)
LEARNING_STAGE_LABELS = {
    "term_understanding": "用語理解",
    "concept_understanding": "概念理解",
    "final_feedback": "教材フィードバック",
}
TEST_PHASES = {"pretest", "retest", "final_test"}
COMPONENT_TERMS = {
    "transfer_learning": ["L3基礎確認"],
    "llm_training_process": ["L3基礎確認"],
}


def _component_terms(term_slug: str, term_label: str) -> list[str]:
    return COMPONENT_TERMS.get(term_slug, [term_label])


def _practice_meta(turn: TutorTurn | None) -> dict[str, Any]:
    if not turn or not isinstance(turn.practice_question_json, dict):
        return {}
    return turn.practice_question_json.get("stage_meta") or {}


def _learning_position(db: Session, session: TutorSession, term: Term, participant: Participant) -> dict[str, Any]:
    components = _component_terms(term.slug, term.label)
    turns = (
        db.query(TutorTurn)
        .filter_by(tutor_session_id=session.id)
        .order_by(TutorTurn.turn_index)
        .all()
    )
    if participant.group_condition == "control":
        for turn in turns:
            if turn.learner_response and bool((turn.grading_json or {}).get("is_sufficient")):
                return {
                    "learning_stage": "final_feedback",
                    "learning_stage_label": LEARNING_STAGE_LABELS["final_feedback"],
                    "component_term": None,
                    "component_index": 1,
                    "component_total": 1,
                }
        return {
            "learning_stage": "concept_understanding",
            "learning_stage_label": LEARNING_STAGE_LABELS["concept_understanding"],
            "component_term": None,
            "component_index": 1,
            "component_total": 1,
        }
    stage = "term_understanding"
    component_index = 0
    for turn in turns:
        if not turn.learner_response:
            continue
        meta = _practice_meta(turn)
        turn_stage = meta.get("learning_stage") or "term_understanding"
        turn_component_index = int(meta.get("component_index") or 0)
        is_sufficient = bool((turn.grading_json or {}).get("is_sufficient"))
        if turn_stage == "term_understanding":
            if is_sufficient and turn_component_index + 1 >= len(components):
                stage = "concept_understanding"
                component_index = len(components)
            elif is_sufficient:
                stage = "term_understanding"
                component_index = turn_component_index + 1
            else:
                stage = "term_understanding"
                component_index = min(turn_component_index, len(components) - 1)
        elif turn_stage == "concept_understanding":
            if is_sufficient:
                stage = "final_feedback"
                component_index = len(components)
            else:
                stage = "term_understanding"
                component_index = 0
    return {
        "learning_stage": stage,
        "learning_stage_label": LEARNING_STAGE_LABELS[stage],
        "component_term": components[component_index] if stage == "term_understanding" else None,
        "component_index": component_index if stage == "term_understanding" else len(components),
        "component_total": len(components),
    }


def _merge_stage_meta(practice_question: dict[str, Any], position: dict[str, Any]) -> dict[str, Any]:
    practice_question = dict(practice_question or {})
    practice_question["stage_meta"] = {
        "learning_stage": position["learning_stage"],
        "learning_stage_label": position["learning_stage_label"],
        "component_term": position["component_term"],
        "component_index": position["component_index"],
        "component_total": position["component_total"],
    }
    return practice_question


def session_misconception_history(db: Session, session_id: str) -> list[dict[str, Any]]:
    turns = (
        db.query(TutorTurn)
        .filter_by(tutor_session_id=session_id)
        .order_by(TutorTurn.turn_index)
        .all()
    )
    history: list[dict[str, Any]] = []
    for turn in turns:
        grading = turn.grading_json or {}
        if not grading or "learning_misconception_type" not in grading:
            continue
        meta = _practice_meta(turn)
        stage = grading.get("learning_stage") or meta.get("learning_stage") or "term_understanding"
        label = grading.get("component_term") or meta.get("component_term") or ("概念理解" if stage == "concept_understanding" else "用語理解")
        history.append(
            {
                "turn_id": turn.id,
                "turn_index": turn.turn_index,
                "learning_stage": stage,
                "label": label,
                "component_term": grading.get("component_term") or meta.get("component_term"),
                "component_index": grading.get("component_index", meta.get("component_index")),
                "misconception_type": grading.get("learning_misconception_type"),
                "confidence": grading.get("learning_misconception_confidence"),
                "reason": grading.get("learning_misconception_reason"),
                "is_sufficient": grading.get("is_sufficient"),
            }
        )
    return history


def latest_learning_misconception(db: Session, session_id: str) -> dict[str, Any] | None:
    history = session_misconception_history(db, session_id)
    return history[-1] if history else None


def _rag_query(*parts: str | None) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


def _rag_context(*parts: str | None) -> dict[str, Any]:
    return retrieve_rag_context(_rag_query(*parts), top_k=3)


def get_participant(db: Session, participant_id: str) -> Participant:
    participant = db.get(Participant, participant_id)
    if not participant:
        raise HTTPException(status_code=404, detail="participant not found")
    return participant


def next_display_code(db: Session) -> str:
    count = db.query(func.count(Participant.id)).scalar() or 0
    return f"P{count + 1:03d}"


def create_participant(db: Session, group_condition: str | None, assignment_method: str, consent_checked: bool) -> Participant:
    if group_condition not in {"control", "proposed"}:
        group_condition = random.choice(["control", "proposed"])
        assignment_method = "random"
    participant = Participant(
        display_code=next_display_code(db),
        group_condition=group_condition,
        assignment_method=assignment_method,
        consent_checked=consent_checked,
        current_step="pretest",
        started_at=now(),
    )
    db.add(participant)
    db.commit()
    db.refresh(participant)
    return participant



def _source_question_phase(phase: str) -> str:
    return phase


def _question_query_for_phase(db: Session, participant: Participant, phase: str):
    source_phase = _source_question_phase(phase)
    query = db.query(Question).join(Term, Question.term_id == Term.id).filter(Question.phase == source_phase, Question.is_active.is_(True), Term.is_active.is_(True))
    if phase == "pretest":
        query = query.filter(Term.slug.in_(PRETEST_TERM_SLUGS))
    if phase == "retest":
        target_term_ids = [
            row.term_id
            for row in db.query(TermAssignment)
            .filter(TermAssignment.participant_id == participant.id, TermAssignment.is_learning_target.is_(True))
            .all()
        ]
        query = query.filter(Question.term_id.in_(target_term_ids or ["__none__"]))
    return query.order_by(Term.display_order, Question.variant_key)


def question_payloads(db: Session, participant_id: str, phase: str) -> list[dict[str, Any]]:
    participant = get_participant(db, participant_id)
    questions = _question_query_for_phase(db, participant, phase).all()
    if phase == "pretest":
        questions = sorted(questions, key=lambda question: PRETEST_TERM_ORDER.get(db.get(Term, question.term_id).slug, 99))
    out = []
    for question in questions:
        term = db.get(Term, question.term_id)
        options = db.query(QuestionOption).filter(QuestionOption.question_id == question.id).order_by(QuestionOption.default_order).all()
        public_options = []
        if options:
            display = db.query(QuestionDisplayOrder).filter_by(participant_id=participant.id, question_id=question.id).one_or_none()
            if not display:
                seed = f"{get_settings().random_seed}:{participant.id}:{question.id}"
                rng = random.Random(seed)
                option_ids = [option.id for option in options]
                rng.shuffle(option_ids)
                display = QuestionDisplayOrder(participant_id=participant.id, question_id=question.id, option_order=option_ids, random_seed=seed)
                db.add(display)
                db.commit()
            option_by_id = {option.id: option for option in options}
            for index, option_id in enumerate(display.option_order):
                option = option_by_id[option_id]
                public_options.append({"option_id": option.id, "label": chr(65 + index), "body": option.body})
        out.append(
            {
                "question_id": question.id,
                "term_slug": term.slug,
                "term_label": term.label,
                "body": _variant_body_for_round(db, participant.id, question, phase),
                "question_type": question.question_type,
                "options": public_options,
                "requires_reason": phase not in {"pretest", "retest", "final_test"},
            }
        )
    return out


def _variant_body_for_round(db: Session, participant_id: str, question: Question, phase: str) -> str:
    if phase != "retest":
        return question.body
    previous_count = (
        db.query(func.count(Attempt.id))
        .filter_by(participant_id=participant_id, question_id=question.id, phase="retest")
        .scalar()
        or 0
    )
    variants = [
        question.body,
        f"別の言い方で確認します。{question.body}",
        f"もう一度、同じ考え方を使って判断してください。{question.body}",
        f"理解が残っているか確認します。{question.body}",
    ]
    return variants[min(previous_count, len(variants) - 1)]


def submit_attempt(db: Session, payload: dict[str, Any], idempotency_key: str | None = None) -> Attempt:
    question = db.get(Question, payload["question_id"])
    if not question:
        raise HTTPException(status_code=404, detail="question not found")
    participant = get_participant(db, payload["participant_id"])
    if idempotency_key:
        existing = db.query(Attempt).filter_by(participant_id=participant.id, idempotency_key=idempotency_key).one_or_none()
        if existing:
            return existing
    phase = payload.get("phase") or question.phase
    is_pretest = phase == "pretest"
    attempt_index = (
        db.query(func.count(Attempt.id))
        .filter_by(participant_id=participant.id, question_id=question.id, phase=phase)
        .scalar()
        or 0
    ) + 1
    attempt = Attempt(
        participant_id=participant.id,
        term_id=question.term_id,
        question_id=question.id,
        phase=phase,
        attempt_index=attempt_index,
        selected_option_id=payload.get("selected_option_id"),
        free_text_answer=None if is_pretest else payload.get("free_text_answer"),
        reason_text=None if is_pretest else payload.get("reason_text"),
        confidence=None,
        response_time_sec=payload.get("response_time_sec"),
        idempotency_key=idempotency_key,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt


async def _ai_call(db: Session, purpose: str, payload: dict[str, Any]) -> dict[str, Any]:
    backend = get_ai_backend()
    started = datetime.now(UTC)
    try:
        result = await getattr(backend, purpose)(payload)
        latency = int((datetime.now(UTC) - started).total_seconds() * 1000)
        db.add(
            AICallLog(
                provider=backend.provider,
                fallback_provider=result.pop("_fallback_provider", None),
                purpose=purpose,
                request_payload=payload,
                response_payload=result,
                status="success",
                latency_ms=latency,
            )
        )
        db.commit()
        return result
    except CodexAppServerError as exc:
        latency = int((datetime.now(UTC) - started).total_seconds() * 1000)
        db.add(
            AICallLog(
                provider=getattr(backend, "provider", "unknown"),
                purpose=purpose,
                request_payload=payload,
                status="failed",
                error_code=exc.code,
                error_message=exc.detail,
                latency_ms=latency,
            )
        )
        db.commit()
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": exc.code,
                "message": exc.user_message,
                "hint": "ホストで `codex app-server --listen ws://127.0.0.1:4500` を起動し、Codex/ChatGPTログイン状態を確認してください。",
            },
        ) from exc
    except Exception as exc:
        db.add(AICallLog(provider=getattr(backend, "provider", "unknown"), purpose=purpose, request_payload=payload, status="failed", error_code="ai_call_failed", error_message=str(exc)))
        db.commit()
        raise


def _selected_option(db: Session, attempt: Attempt) -> QuestionOption | None:
    return db.get(QuestionOption, attempt.selected_option_id) if attempt.selected_option_id else None


def _diagnosis_payload(db: Session, participant: Participant, attempt: Attempt) -> dict[str, Any]:
    question = db.get(Question, attempt.question_id)
    term = db.get(Term, attempt.term_id)
    option = _selected_option(db, attempt)
    payload = {
        "participant_id": participant.id,
        "group_condition": participant.group_condition,
        "term": {"slug": term.slug, "label": term.label, "definition": term.description},
        "question": {"id": question.id, "phase": question.phase, "question_type": question.question_type, "body": question.body, "expected_answer": question.expected_answer},
        "selected_option": None
        if not option
        else {"id": option.id, "body": option.body, "is_correct": option.is_correct, "initial_misconception_type": option.misconception_type},
        "history": {"previous_attempts": []},
    }
    if question.phase != "pretest":
        payload["learner_response"] = {"reason_text": attempt.reason_text, "free_text_answer": attempt.free_text_answer}
    return payload


def _public_summary(text: str | None) -> str:
    cleaned = text or "この用語を重点的に確認します。"
    cleaned = re.sub(r"理由記述(や自信度)?(も)?ないため、?", "", cleaned)
    cleaned = re.sub(r"理由記述(や自信度)?(も)?ないので、?", "", cleaned)
    cleaned = re.sub(r"理由記述や自信度", "回答内容", cleaned)
    cleaned = re.sub(r"理由記述", "回答内容", cleaned)
    cleaned = re.sub(r"自信度", "", cleaned)
    cleaned = re.sub(r"、{2,}", "、", cleaned)
    cleaned = re.sub(r"。{2,}", "。", cleaned)
    return cleaned.strip("、 ") or "この用語を重点的に確認します。"


def _priority(attempt: Attempt) -> tuple[float, str]:
    term_order_bonus = 0
    if attempt.diagnosed_status == "misconception":
        score = 70 + term_order_bonus
        if attempt.misconception_type in {"M1", "M2"}:
            score += 20
        elif attempt.misconception_type == "M3":
            score += 10
        return score, f"{attempt.misconception_type}を重点確認"
    if attempt.diagnosed_status == "unknown":
        return 55 + term_order_bonus, "基礎理解を確認"
    if attempt.diagnosed_status == "unstable_correct":
        return 45 + term_order_bonus, "理解を確認"
    return 10 + term_order_bonus, "転移準備"


async def diagnose_pretest(db: Session, participant_id: str) -> int:
    participant = get_participant(db, participant_id)
    attempts = db.query(Attempt).filter_by(participant_id=participant.id, phase="pretest").all()
    if not attempts:
        raise HTTPException(status_code=400, detail="pretest attempts not found")

    scored_attempts: list[Attempt] = []
    for attempt in attempts:
        result = await _ai_call(db, "diagnose_answer", _diagnosis_payload(db, participant, attempt))
        attempt.is_correct = result["is_correct"]
        attempt.score = 1.0 if result["is_correct"] else 0.0
        attempt.diagnosed_status = result["diagnosed_status"]
        attempt.misconception_type = result["misconception_type"]
        attempt.secondary_misconception_type = result["secondary_misconception_type"]
        attempt.misconception_confidence = result["diagnosis_confidence"]
        attempt.natural_language_diagnosis = result["natural_language_diagnosis"]
        attempt.requires_manual_review = result["requires_manual_review"]
        state = db.query(LearnerState).filter_by(participant_id=participant.id, term_id=attempt.term_id).one_or_none()
        if not state:
            state = LearnerState(participant_id=participant.id, term_id=attempt.term_id, current_status=result["diagnosed_status"], primary_misconception=result["misconception_type"], secondary_misconception=result["secondary_misconception_type"], scaffolding_level=result["recommended_initial_scaffolding_level"], teaching_strategy=result["recommended_teaching_strategy"], last_attempt_id=attempt.id, state_summary=result["natural_language_diagnosis"])
            db.add(state)
        scored_attempts.append(attempt)
    db.commit()

    for attempt in scored_attempts:
        existing = db.query(TermAssignment).filter_by(participant_id=participant.id, term_id=attempt.term_id).one_or_none()
        score, reason = _priority(attempt)
        if not existing:
            db.add(TermAssignment(participant_id=participant.id, term_id=attempt.term_id, group_condition=participant.group_condition, priority_score=score, selection_reason=reason))
        else:
            existing.priority_score = score
            existing.selection_reason = reason
    db.commit()

    assignments = (
        db.query(TermAssignment)
        .filter_by(participant_id=participant.id)
        .order_by(TermAssignment.priority_score.desc())
        .all()
    )
    latest_attempt_by_term = {attempt.term_id: attempt for attempt in scored_attempts}
    for index, assignment in enumerate(assignments):
        latest_attempt = latest_attempt_by_term.get(assignment.term_id)
        assignment.is_learning_target = bool(latest_attempt and not latest_attempt.is_correct and index < get_settings().max_learning_targets)
    remaining = sum(1 for assignment in assignments if assignment.is_learning_target)
    participant.current_step = "learning_targets" if remaining else "final_test"
    db.commit()
    return remaining


def learning_targets(db: Session, participant_id: str) -> list[dict[str, Any]]:
    participant = get_participant(db, participant_id)
    rows = (
        db.query(TermAssignment, Term, LearnerState)
        .join(Term, TermAssignment.term_id == Term.id)
        .join(LearnerState, (LearnerState.term_id == Term.id) & (LearnerState.participant_id == participant.id))
        .filter(TermAssignment.participant_id == participant.id, TermAssignment.is_learning_target.is_(True))
        .order_by(TermAssignment.priority_score.desc())
        .all()
    )
    return [
        {
            "term_slug": term.slug,
            "term_label": term.label,
            "summary_for_learner": _public_summary(state.state_summary),
            "current_stage_for_display": PUBLIC_LEVEL.get(normalize_level(state.scaffolding_level), "概念理解を確認"),
        }
        for _, term, state in rows
    ]


def create_tutor_session(db: Session, participant_id: str, term_slug: str) -> TutorSession:
    participant = get_participant(db, participant_id)
    term = db.query(Term).filter_by(slug=term_slug).one_or_none()
    if not term:
        raise HTTPException(status_code=404, detail="term not found")
    count = db.query(func.count(TutorSession.id)).filter_by(participant_id=participant.id, term_id=term.id).scalar() or 0
    session = TutorSession(participant_id=participant.id, term_id=term.id, session_index=count + 1, group_condition=participant.group_condition)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


async def generate_tutor_turn(db: Session, session_id: str) -> TutorTurn:
    session = db.get(TutorSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    participant = get_participant(db, session.participant_id)
    term = db.get(Term, session.term_id)
    state = db.query(LearnerState).filter_by(participant_id=participant.id, term_id=term.id).one()
    previous_attempt = db.get(Attempt, state.last_attempt_id) if state.last_attempt_id else None
    previous_turn = db.get(TutorTurn, state.last_tutor_turn_id) if state.last_tutor_turn_id else None
    turn_count = db.query(func.count(TutorTurn.id)).filter_by(tutor_session_id=session.id).scalar() or 0
    position = _learning_position(db, session, term, participant)
    if position["learning_stage"] == "final_feedback":
        raise HTTPException(status_code=400, detail="learning session already completed")
    current_level = normalize_level(state.scaffolding_level)
    misconception_history = session_misconception_history(db, session.id)
    previous_learning_misconception = misconception_history[-1] if misconception_history else None
    effective_misconception = (previous_learning_misconception or {}).get("misconception_type") or state.primary_misconception
    effective_status = "unknown" if effective_misconception == "unknown" else ("misconception" if effective_misconception else state.current_status)
    effective_strategy = strategy_for(effective_misconception, effective_status, participant.group_condition)
    payload = {
        "participant_id": participant.id,
        "group_condition": participant.group_condition,
        "term": {"slug": term.slug, "label": term.label, "description": term.description},
        "learning_stage": position["learning_stage"],
        "learning_stage_label": position["learning_stage_label"],
        "component_term": position["component_term"],
        "component_index": position["component_index"],
        "component_total": position["component_total"],
        "component_terms": _component_terms(term.slug, term.label),
        "learner_state": {
            "current_status": state.current_status,
            "primary_misconception": state.primary_misconception,
            "scaffolding_level": current_level,
            "teaching_strategy": effective_strategy,
            "recurrence_count": state.recurrence_count,
        },
        "previous_answer": previous_attempt.reason_text if previous_attempt else "",
        "previous_diagnosis_for_learner": state.state_summary,
        "previous_practice_question": (previous_turn.practice_question_json or {}).get("body") if previous_turn else "",
        "previous_learner_response": previous_turn.learner_response if previous_turn else "",
        "previous_feedback_for_learner": previous_turn.ai_feedback if previous_turn else "",
        "previous_learning_misconception": previous_learning_misconception if participant.group_condition == "proposed" else None,
        "session_misconception_history": misconception_history if participant.group_condition == "proposed" else [],
        "rag_context": _rag_context(
            term.label,
            term.description,
            position["component_term"],
            previous_attempt.reason_text if previous_attempt else "",
            (previous_turn.practice_question_json or {}).get("body") if previous_turn else "",
            previous_turn.learner_response if previous_turn else "",
        ),
    }
    result = await _ai_call(db, "generate_tutoring_turn", payload)
    turn = TutorTurn(
        tutor_session_id=session.id,
        turn_index=turn_count + 1,
        scaffolding_level=current_level,
        teaching_strategy=("general_explanation" if participant.group_condition == "control" else result["teaching_strategy"]),
        previous_teaching_strategy=state.previous_teaching_strategy,
        strategy_changed=False,
        tutor_message=result["tutor_message"],
        learner_prompt=result["learner_prompt"],
        practice_question_json=_merge_stage_meta(result["practice_question"], position),
        forbidden_help_given=result["forbidden_help_given"],
    )
    db.add(turn)
    db.commit()
    db.refresh(turn)
    return turn

async def respond_tutor_turn(db: Session, turn_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    turn = db.get(TutorTurn, turn_id)
    if not turn:
        raise HTTPException(status_code=404, detail="turn not found")
    session = db.get(TutorSession, turn.tutor_session_id)
    state = db.query(LearnerState).filter_by(participant_id=session.participant_id, term_id=session.term_id).one()
    response = payload.get("learner_response") or ""
    participant = get_participant(db, session.participant_id)
    term = db.get(Term, session.term_id)
    meta = _practice_meta(turn)
    learning_stage = meta.get("learning_stage") or "term_understanding"
    component_index = int(meta.get("component_index") or 0)
    component_total = int(meta.get("component_total") or len(_component_terms(term.slug, term.label)))
    component_term = meta.get("component_term")
    feedback_payload = {
        "participant_id": participant.id,
        "group_condition": participant.group_condition,
        "term": {"slug": term.slug, "label": term.label, "description": term.description},
        "learning_stage": learning_stage,
        "learning_stage_label": meta.get("learning_stage_label") or LEARNING_STAGE_LABELS.get(learning_stage, "用語理解"),
        "component_term": component_term,
        "component_index": component_index,
        "component_total": component_total,
        "component_terms": _component_terms(term.slug, term.label),
        "learner_state": {
            "current_status": state.current_status,
            "primary_misconception": state.primary_misconception if participant.group_condition == "proposed" else None,
            "scaffolding_level": normalize_level(state.scaffolding_level),
            "teaching_strategy": state.teaching_strategy,
            "recurrence_count": state.recurrence_count,
        },
        "tutor_turn": {
            "turn_index": turn.turn_index,
            "tutor_message": turn.tutor_message,
            "learner_prompt": turn.learner_prompt,
            "practice_question": turn.practice_question_json,
        },
        "learner_response": response,
        "rag_context": _rag_context(
            term.label,
            term.description,
            component_term,
            (turn.practice_question_json or {}).get("body"),
            response,
        ),
    }
    result = await _ai_call(db, "generate_feedback", feedback_payload)
    is_sufficient = bool(result.get("is_sufficient"))
    learning_misconception_type = result.get("learning_misconception_type")
    if learning_misconception_type not in {"M1", "M2", "M3", "M4", "unknown", None}:
        learning_misconception_type = "unknown"
    learning_misconception_confidence = result.get("learning_misconception_confidence")
    learning_misconception_reason = result.get("learning_misconception_reason") or result.get("state_update_reason") or ""
    next_level = normalize_level(lower_level(state.scaffolding_level) if is_sufficient else raise_level(state.scaffolding_level))
    if learning_stage == "term_understanding":
        stage_completed = is_sufficient and component_index + 1 >= component_total
        next_learning_stage = "concept_understanding" if stage_completed else "term_understanding"
        next_component_index = component_total if stage_completed else (component_index + 1 if is_sufficient else component_index)
        session_completed = False
        next_action = "continue"
    elif learning_stage == "concept_understanding":
        stage_completed = is_sufficient
        next_learning_stage = "final_feedback" if is_sufficient else ("concept_understanding" if participant.group_condition == "control" else "term_understanding")
        next_component_index = component_total if is_sufficient else (component_total if participant.group_condition == "control" else 0)
        session_completed = is_sufficient
        next_action = "move_next" if is_sufficient else "continue"
    else:
        stage_completed = True
        next_learning_stage = "final_feedback"
        next_component_index = component_total
        session_completed = True
        next_action = "move_next"
    turn.learner_response = response
    turn.learner_confidence = None
    turn.next_scaffolding_level = next_level
    turn.ai_feedback = result["feedback"]
    turn.grading_json = {
        "is_sufficient": is_sufficient,
        "learning_stage": learning_stage,
        "component_term": component_term,
        "component_index": component_index,
        "component_total": component_total,
        "stage_completed": stage_completed,
        "next_learning_stage": next_learning_stage,
        "next_component_index": next_component_index,
        "learning_misconception_type": learning_misconception_type,
        "learning_misconception_confidence": learning_misconception_confidence,
        "learning_misconception_reason": learning_misconception_reason,
        "ai_next_action": result.get("next_action"),
    }
    state.scaffolding_level = next_level
    state.stable_correct_count += 1 if is_sufficient else 0
    state.current_status = "stable_correct" if session_completed else ("learning_in_progress" if is_sufficient else "needs_review")
    state.updated_reason = result["state_update_reason"]
    state.last_tutor_turn_id = turn.id
    if session_completed:
        session.ended_at = now()
    db.commit()
    return {
        "feedback": turn.ai_feedback,
        "next_action": next_action,
        "is_sufficient": is_sufficient,
        "session_completed": session_completed,
        "learning_stage": learning_stage,
        "stage_completed": stage_completed,
        "next_learning_stage": next_learning_stage,
        "component_term": component_term,
        "component_index": component_index,
        "component_total": component_total,
        "next_component_index": next_component_index,
        "learning_misconception_type": learning_misconception_type,
        "learning_misconception_confidence": learning_misconception_confidence,
        "learning_misconception_reason": learning_misconception_reason,
        "next_scaffolding_level": next_level,
        "turn_index": turn.turn_index,
        "max_turns": get_settings().max_turns_per_term,
    }

async def score_phase(db: Session, participant_id: str, phase: str) -> dict[str, Any]:
    participant = get_participant(db, participant_id)
    attempts = db.query(Attempt).filter_by(participant_id=participant.id, phase=phase, is_correct=None).all()
    if not attempts:
        raise HTTPException(status_code=400, detail=f"{phase} attempts not found")
    for attempt in attempts:
        question = db.get(Question, attempt.question_id)
        option = _selected_option(db, attempt)
        payload = {
            "participant_id": participant.id,
            "group_condition": participant.group_condition,
            "question": {"id": question.id, "phase": phase, "body": question.body, "expected_answer": question.expected_answer, "expected_keywords": question.expected_keywords},
            "selected_option": None if not option else {"id": option.id, "body": option.body, "is_correct": option.is_correct, "initial_misconception_type": option.misconception_type},
            "free_text_answer": attempt.free_text_answer,
            "reason_text": attempt.reason_text,
        }
        if phase in {"retest", "final_test"} and option:
            result = {
                "is_correct": bool(option.is_correct),
                "score": 1.0 if option.is_correct else 0.0,
                "diagnosed_status": "stable_correct" if option.is_correct else ("unknown" if option.misconception_type == "unknown" else "misconception"),
                "misconception_type": None if option.is_correct else option.misconception_type,
                "secondary_misconception_type": None,
                "l0_success": bool(option.is_correct),
            }
        else:
            result = await _ai_call(db, "grade_response", payload)
        attempt.is_correct = result["is_correct"]
        attempt.score = result["score"]
        attempt.diagnosed_status = result["diagnosed_status"]
        attempt.misconception_type = result["misconception_type"]
        attempt.secondary_misconception_type = result["secondary_misconception_type"]
        attempt.l0_success = result["l0_success"] if result.get("l0_success") is not None else (result["is_correct"] if phase == "final_test" else None)
        state = db.query(LearnerState).filter_by(participant_id=participant.id, term_id=attempt.term_id).one_or_none()
        if not state:
            continue
        if phase == "retest":
            previous = db.query(Attempt).filter_by(participant_id=participant.id, term_id=attempt.term_id, phase="pretest").order_by(Attempt.created_at.desc()).first()
            if previous and previous.misconception_type in {"M1", "M2", "M3"} and previous.misconception_type == attempt.misconception_type:
                attempt.recurrence_flag = True
                state.recurrence_count += 1
                state.previous_teaching_strategy = state.teaching_strategy
                state.teaching_strategy = strategy_for(attempt.misconception_type, "misconception", participant.group_condition)
                db.add(RecurrenceEvent(participant_id=participant.id, term_id=attempt.term_id, previous_attempt_id=previous.id, current_attempt_id=attempt.id, previous_misconception_type=previous.misconception_type, current_misconception_type=attempt.misconception_type, is_same_type=True, phase=phase))
            state.scaffolding_level = lower_level(state.scaffolding_level) if attempt.is_correct else state.scaffolding_level
            assignment = db.query(TermAssignment).filter_by(participant_id=participant.id, term_id=attempt.term_id).one_or_none()
            if assignment:
                assignment.is_learning_target = not bool(attempt.is_correct)
                if attempt.is_correct:
                    assignment.priority_score = 0
                    assignment.selection_reason = "正解したため次周回から除外"
                else:
                    assignment.priority_score, assignment.selection_reason = _priority(attempt)
        if phase in {"l0_check", "final_test"}:
            state.l0_success_count += 1 if attempt.is_correct else 0
            state.scaffolding_level = "L2" if attempt.is_correct else "L3"
        state.current_status = "stable_correct" if attempt.is_correct else "misconception"
        state.last_attempt_id = attempt.id
    if phase == "retest":
        db.flush()
        remaining = db.query(func.count(TermAssignment.id)).filter_by(participant_id=participant.id, is_learning_target=True).scalar() or 0
        participant.current_step = "learning_targets" if remaining else "final_test"
    elif phase == "l0_check":
        participant.current_step = "finish"
        participant.completed_at = now()
    elif phase == "final_test":
        participant.current_step = "survey"
    db.commit()
    return {"status": "completed", "next_step": participant.current_step, "next_url": _next_url(participant.current_step)}


def _next_url(step: str) -> str:
    return {
        "pretest": "/pretest",
        "learning_targets": "/learning-targets",
        "final_test": "/final-test",
        "survey": "/survey",
        "finish": "/finish",
    }.get(step, "/start")


def _rate(items: list[Attempt], predicate) -> float | None:
    if not items:
        return None
    return sum(1 for item in items if predicate(item)) / len(items)


def recalculate_evaluation(db: Session, participant_id: str) -> EvaluationSummary:
    participant = get_participant(db, participant_id)
    attempts = db.query(Attempt).filter_by(participant_id=participant.id).all()
    by_phase = {phase: [a for a in attempts if a.phase == phase] for phase in ["pretest", "retest", "l0_check", "final_test"]}
    final_items = by_phase["final_test"] or by_phase["l0_check"]
    initial_m = [a for a in by_phase["pretest"] if a.misconception_type in {"M1", "M2", "M3"}]
    same_rec = [a for a in by_phase["retest"] if a.recurrence_flag]
    def m_rate(m: str) -> float | None:
        denom = [a for a in initial_m if a.misconception_type == m]
        if not denom:
            return None
        rec_terms = {a.term_id for a in by_phase["retest"] if a.recurrence_flag and a.misconception_type == m}
        return len(rec_terms) / len(denom)

    summary = EvaluationSummary(
        participant_id=participant.id,
        group_condition=participant.group_condition,
        pretest_score=_rate(by_phase["pretest"], lambda a: bool(a.is_correct)),
        retest_score=_rate(by_phase["retest"], lambda a: bool(a.is_correct)),
        l0_correct_rate=_rate(final_items, lambda a: bool(a.l0_success)),
        transfer_correct_rate=None,
        same_misconception_recurrence_rate=(len(same_rec) / len(initial_m)) if initial_m else None,
        m1_recurrence_rate=m_rate("M1"),
        m2_recurrence_rate=m_rate("M2"),
        m3_recurrence_rate=m_rate("M3"),
        m4_failure_rate=None,
        unknown_persistence_rate=None,
        learning_target_count=db.query(func.count(TermAssignment.id)).filter_by(participant_id=participant.id, is_learning_target=True).scalar() or 0,
        completed=participant.completed_at is not None,
    )
    db.add(summary)
    db.commit()
    db.refresh(summary)
    return summary


def admin_summary(db: Session) -> dict[str, Any]:
    participants = db.query(Participant).all()
    rows = []
    for group in ["control", "proposed"]:
        group_participants = [p for p in participants if p.group_condition == group]
        latest_summaries = []
        for p in group_participants:
            s = db.query(EvaluationSummary).filter_by(participant_id=p.id).order_by(EvaluationSummary.created_at.desc()).first()
            if s:
                latest_summaries.append(s)
        def avg(attr: str):
            vals = [getattr(s, attr) for s in latest_summaries if getattr(s, attr) is not None]
            return sum(vals) / len(vals) if vals else None
        rows.append(
            {
                "group_condition": group,
                "participant_count": len(group_participants),
                "same_misconception_recurrence_rate": avg("same_misconception_recurrence_rate"),
                "l0_correct_rate": avg("l0_correct_rate"),
            }
        )
    return {"groups": rows}


EXPORTS = {
    "participants": (Participant, ["id", "display_code", "group_condition", "assignment_method", "current_step", "started_at", "completed_at"]),
    "attempts": (Attempt, ["id", "participant_id", "term_id", "phase", "question_id", "selected_option_id", "reason_text", "free_text_answer", "is_correct", "score", "diagnosed_status", "misconception_type", "recurrence_flag", "l0_success", "requires_manual_review", "created_at"]),
    "learner_states": (LearnerState, ["participant_id", "term_id", "current_status", "primary_misconception", "scaffolding_level", "teaching_strategy", "stable_correct_count", "recurrence_count", "l0_success_count", "updated_at"]),
    "tutor_sessions": (TutorSession, ["id", "participant_id", "term_id", "session_index", "group_condition", "started_at", "ended_at"]),
    "tutor_turns": (TutorTurn, ["id", "tutor_session_id", "turn_index", "scaffolding_level", "teaching_strategy", "strategy_changed", "tutor_message", "learner_response", "ai_feedback", "next_scaffolding_level", "forbidden_help_given", "created_at"]),
    "recurrence_events": (RecurrenceEvent, ["id", "participant_id", "term_id", "previous_attempt_id", "current_attempt_id", "previous_misconception_type", "current_misconception_type", "is_same_type", "phase", "created_at"]),
    "ai_call_logs": (AICallLog, ["id", "provider", "fallback_provider", "purpose", "status", "error_code", "latency_ms", "created_at"]),
    "evaluation_summary": (EvaluationSummary, ["participant_id", "group_condition", "pretest_score", "retest_score", "l0_correct_rate", "same_misconception_recurrence_rate", "m1_recurrence_rate", "m2_recurrence_rate", "m3_recurrence_rate", "learning_target_count", "completed", "created_at"]),
}


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _term_map(db: Session) -> dict[str, Term]:
    return {term.id: term for term in db.query(Term).all()}


def _participant_map(db: Session) -> dict[str, Participant]:
    return {participant.id: participant for participant in db.query(Participant).all()}


def _option_map(db: Session) -> dict[str, QuestionOption]:
    return {option.id: option for option in db.query(QuestionOption).all()}


def _question_map(db: Session) -> dict[str, Question]:
    return {question.id: question for question in db.query(Question).all()}


def _attempt_log_row(
    attempt: Attempt,
    participants: dict[str, Participant],
    terms: dict[str, Term],
    questions: dict[str, Question],
    options: dict[str, QuestionOption],
) -> dict[str, Any]:
    participant = participants.get(attempt.participant_id)
    term = terms.get(attempt.term_id)
    question = questions.get(attempt.question_id)
    option = options.get(attempt.selected_option_id or "")
    return {
        "attempt_id": attempt.id,
        "participant_id": attempt.participant_id,
        "display_code": participant.display_code if participant else None,
        "group_condition": participant.group_condition if participant else None,
        "phase": attempt.phase,
        "term_slug": term.slug if term else None,
        "term_label": term.label if term else None,
        "question_body": question.body if question else None,
        "selected_option_body": option.body if option else None,
        "free_text_answer": attempt.free_text_answer,
        "reason_text": attempt.reason_text,
        "is_correct": attempt.is_correct,
        "score": attempt.score,
        "diagnosed_status": attempt.diagnosed_status,
        "misconception_type": attempt.misconception_type,
        "recurrence_flag": attempt.recurrence_flag,
        "l0_success": attempt.l0_success,
        "requires_manual_review": attempt.requires_manual_review,
        "created_at": _iso(attempt.created_at),
    }


def _turn_log_row(turn: TutorTurn, session: TutorSession, participant: Participant | None, term: Term | None) -> dict[str, Any]:
    stage_meta = (turn.practice_question_json or {}).get("stage_meta") or {}
    grading = turn.grading_json or {}
    return {
        "tutor_turn_id": turn.id,
        "tutor_session_id": turn.tutor_session_id,
        "participant_id": session.participant_id,
        "display_code": participant.display_code if participant else None,
        "group_condition": session.group_condition,
        "term_slug": term.slug if term else None,
        "term_label": term.label if term else None,
        "session_index": session.session_index,
        "turn_index": turn.turn_index,
        "scaffolding_level": turn.scaffolding_level,
        "learning_stage": stage_meta.get("learning_stage"),
        "learning_stage_label": stage_meta.get("learning_stage_label"),
        "component_term": stage_meta.get("component_term"),
        "component_index": stage_meta.get("component_index"),
        "component_total": stage_meta.get("component_total"),
        "next_learning_stage": grading.get("next_learning_stage"),
        "teaching_strategy": turn.teaching_strategy,
        "strategy_changed": turn.strategy_changed,
        "tutor_message": turn.tutor_message,
        "learner_prompt": turn.learner_prompt,
        "learner_response": turn.learner_response,
        "ai_feedback": turn.ai_feedback,
        "practice_question": turn.practice_question_json,
        "grading_json": turn.grading_json,
        "forbidden_help_given": turn.forbidden_help_given,
        "created_at": _iso(turn.created_at),
    }


def _ai_log_belongs_to(log: AICallLog, participant_id: str) -> bool:
    payload = log.request_payload or {}
    return payload.get("participant_id") == participant_id


def admin_logs_overview(db: Session) -> dict[str, Any]:
    participants = db.query(Participant).order_by(Participant.created_at.desc()).all()
    participant_by_id = {participant.id: participant for participant in participants}
    terms = _term_map(db)
    questions = _question_map(db)
    options = _option_map(db)
    attempts = db.query(Attempt).order_by(Attempt.created_at.desc()).limit(50).all()
    sessions = {session.id: session for session in db.query(TutorSession).all()}
    recent_turns = db.query(TutorTurn).order_by(TutorTurn.created_at.desc()).limit(30).all()
    ai_logs = db.query(AICallLog).order_by(AICallLog.created_at.desc()).limit(50).all()
    recurrences = db.query(RecurrenceEvent).order_by(RecurrenceEvent.created_at.desc()).limit(30).all()
    summaries = db.query(EvaluationSummary).order_by(EvaluationSummary.created_at.desc()).limit(30).all()
    return {
        "participant_count": len(participants),
        "groups": admin_summary(db)["groups"],
        "participants": [
            {
                "participant_id": row.id,
                "display_code": row.display_code,
                "group_condition": row.group_condition,
                "current_step": row.current_step,
                "completed_at": _iso(row.completed_at),
                "created_at": _iso(row.created_at),
            }
            for row in participants
        ],
        "recent_attempts": [_attempt_log_row(row, participant_by_id, terms, questions, options) for row in attempts],
        "recent_tutor_turns": [
            _turn_log_row(row, sessions[row.tutor_session_id], participant_by_id.get(sessions[row.tutor_session_id].participant_id), terms.get(sessions[row.tutor_session_id].term_id))
            for row in recent_turns
            if row.tutor_session_id in sessions
        ],
        "recent_ai_call_logs": [
            {
                "id": row.id,
                "provider": row.provider,
                "purpose": row.purpose,
                "status": row.status,
                "error_code": row.error_code,
                "error_message": row.error_message,
                "latency_ms": row.latency_ms,
                "created_at": _iso(row.created_at),
            }
            for row in ai_logs
        ],
        "recurrence_events": [
            {
                "id": row.id,
                "participant_id": row.participant_id,
                "display_code": participant_by_id.get(row.participant_id).display_code if participant_by_id.get(row.participant_id) else None,
                "term_slug": terms.get(row.term_id).slug if terms.get(row.term_id) else None,
                "previous_misconception_type": row.previous_misconception_type,
                "current_misconception_type": row.current_misconception_type,
                "phase": row.phase,
                "created_at": _iso(row.created_at),
            }
            for row in recurrences
        ],
        "evaluation_summaries": [
            {
                "participant_id": row.participant_id,
                "display_code": participant_by_id.get(row.participant_id).display_code if participant_by_id.get(row.participant_id) else None,
                "group_condition": row.group_condition,
                "pretest_score": row.pretest_score,
                "retest_score": row.retest_score,
                "l0_correct_rate": row.l0_correct_rate,
                "same_misconception_recurrence_rate": row.same_misconception_recurrence_rate,
                "completed": row.completed,
                "created_at": _iso(row.created_at),
            }
            for row in summaries
        ],
    }


def participant_logs(db: Session, participant_id: str) -> dict[str, Any]:
    participant = get_participant(db, participant_id)
    participants = {participant.id: participant}
    terms = _term_map(db)
    questions = _question_map(db)
    options = _option_map(db)
    attempts = db.query(Attempt).filter_by(participant_id=participant.id).order_by(Attempt.created_at).all()
    states = db.query(LearnerState).filter_by(participant_id=participant.id).order_by(LearnerState.updated_at).all()
    assignments = db.query(TermAssignment).filter_by(participant_id=participant.id).all()
    sessions = db.query(TutorSession).filter_by(participant_id=participant.id).order_by(TutorSession.started_at).all()
    session_ids = [session.id for session in sessions]
    turns = db.query(TutorTurn).filter(TutorTurn.tutor_session_id.in_(session_ids or ["__none__"])).order_by(TutorTurn.created_at).all()
    turns_by_session: dict[str, list[TutorTurn]] = {}
    for turn in turns:
        turns_by_session.setdefault(turn.tutor_session_id, []).append(turn)
    recurrences = db.query(RecurrenceEvent).filter_by(participant_id=participant.id).order_by(RecurrenceEvent.created_at).all()
    ai_logs = [row for row in db.query(AICallLog).order_by(AICallLog.created_at).all() if _ai_log_belongs_to(row, participant.id)]
    summary = db.query(EvaluationSummary).filter_by(participant_id=participant.id).order_by(EvaluationSummary.created_at.desc()).first()
    return {
        "participant": {
            "participant_id": participant.id,
            "display_code": participant.display_code,
            "group_condition": participant.group_condition,
            "assignment_method": participant.assignment_method,
            "current_step": participant.current_step,
            "started_at": _iso(participant.started_at),
            "completed_at": _iso(participant.completed_at),
            "created_at": _iso(participant.created_at),
        },
        "attempts": [_attempt_log_row(row, participants, terms, questions, options) for row in attempts],
        "learner_states": [
            {
                "term_slug": terms.get(row.term_id).slug if terms.get(row.term_id) else None,
                "term_label": terms.get(row.term_id).label if terms.get(row.term_id) else None,
                "current_status": row.current_status,
                "primary_misconception": row.primary_misconception,
                "scaffolding_level": row.scaffolding_level,
                "current_stage_for_display": PUBLIC_LEVEL.get(normalize_level(row.scaffolding_level), "概念理解を確認"),
                "teaching_strategy": row.teaching_strategy,
                "stable_correct_count": row.stable_correct_count,
                "recurrence_count": row.recurrence_count,
                "l0_success_count": row.l0_success_count,
                "state_summary": row.state_summary,
                "updated_at": _iso(row.updated_at),
            }
            for row in states
        ],
        "term_assignments": [
            {
                "term_slug": terms.get(row.term_id).slug if terms.get(row.term_id) else None,
                "term_label": terms.get(row.term_id).label if terms.get(row.term_id) else None,
                "is_learning_target": row.is_learning_target,
                "selection_reason": row.selection_reason,
                "priority_score": row.priority_score,
                "created_at": _iso(row.created_at),
            }
            for row in assignments
        ],
        "tutor_sessions": [
            {
                "tutor_session_id": session.id,
                "term_slug": terms.get(session.term_id).slug if terms.get(session.term_id) else None,
                "term_label": terms.get(session.term_id).label if terms.get(session.term_id) else None,
                "session_index": session.session_index,
                "group_condition": session.group_condition,
                "started_at": _iso(session.started_at),
                "ended_at": _iso(session.ended_at),
                "turns": [_turn_log_row(turn, session, participant, terms.get(session.term_id)) for turn in turns_by_session.get(session.id, [])],
            }
            for session in sessions
        ],
        "recurrence_events": [
            {
                "id": row.id,
                "term_slug": terms.get(row.term_id).slug if terms.get(row.term_id) else None,
                "previous_misconception_type": row.previous_misconception_type,
                "current_misconception_type": row.current_misconception_type,
                "is_same_type": row.is_same_type,
                "phase": row.phase,
                "created_at": _iso(row.created_at),
            }
            for row in recurrences
        ],
        "ai_call_logs": [
            {
                "id": row.id,
                "provider": row.provider,
                "purpose": row.purpose,
                "status": row.status,
                "error_code": row.error_code,
                "error_message": row.error_message,
                "latency_ms": row.latency_ms,
                "request_payload": row.request_payload,
                "response_payload": row.response_payload,
                "created_at": _iso(row.created_at),
            }
            for row in ai_logs
        ],
        "latest_evaluation_summary": None
        if not summary
        else {
            "pretest_score": summary.pretest_score,
            "retest_score": summary.retest_score,
            "l0_correct_rate": summary.l0_correct_rate,
            "same_misconception_recurrence_rate": summary.same_misconception_recurrence_rate,
            "m1_recurrence_rate": summary.m1_recurrence_rate,
            "m2_recurrence_rate": summary.m2_recurrence_rate,
            "m3_recurrence_rate": summary.m3_recurrence_rate,
            "learning_target_count": summary.learning_target_count,
            "completed": summary.completed,
            "created_at": _iso(summary.created_at),
        },
    }


LOG_CSV_COLUMNS = ["record_type", "participant_id", "display_code", "phase", "term_slug", "event_time", "summary", "value_json"]


def _csv_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _log_csv_rows_from_participant_logs(logs: dict[str, Any]) -> list[dict[str, Any]]:
    participant = logs["participant"]
    rows: list[dict[str, Any]] = []
    base = {"participant_id": participant["participant_id"], "display_code": participant["display_code"]}
    for attempt in logs["attempts"]:
        rows.append({**base, "record_type": "attempt", "phase": attempt["phase"], "term_slug": attempt["term_slug"], "event_time": attempt["created_at"], "summary": f"{attempt['term_label']} {attempt['phase']} correct={attempt['is_correct']} m={attempt['misconception_type']}", "value_json": _csv_value(attempt)})
    for state in logs["learner_states"]:
        rows.append({**base, "record_type": "learner_state", "phase": "state", "term_slug": state["term_slug"], "event_time": state["updated_at"], "summary": f"{state['term_label']} status={state['current_status']} stage={state['current_stage_for_display']} strategy={state['teaching_strategy']}", "value_json": _csv_value(state)})
    for session in logs["tutor_sessions"]:
        rows.append({**base, "record_type": "tutor_session", "phase": "learning", "term_slug": session["term_slug"], "event_time": session["started_at"], "summary": f"{session['term_label']} session {session['session_index']}", "value_json": _csv_value({k: v for k, v in session.items() if k != "turns"})})
        for turn in session["turns"]:
            rows.append({**base, "record_type": "tutor_turn", "phase": "learning", "term_slug": turn["term_slug"], "event_time": turn["created_at"], "summary": f"{turn['term_label']} turn {turn['turn_index']} stage={turn['learning_stage']} component={turn['component_term']} strategy={turn['teaching_strategy']}", "value_json": _csv_value(turn)})
    for event in logs["recurrence_events"]:
        rows.append({**base, "record_type": "recurrence", "phase": event["phase"], "term_slug": event["term_slug"], "event_time": event["created_at"], "summary": f"{event['previous_misconception_type']} -> {event['current_misconception_type']}", "value_json": _csv_value(event)})
    for call in logs["ai_call_logs"]:
        rows.append({**base, "record_type": "ai_call", "phase": "", "term_slug": "", "event_time": call["created_at"], "summary": f"{call['purpose']} {call['status']} {call['error_code'] or ''}".strip(), "value_json": _csv_value(call)})
    if logs["latest_evaluation_summary"]:
        rows.append({**base, "record_type": "evaluation_summary", "phase": "summary", "term_slug": "", "event_time": logs["latest_evaluation_summary"]["created_at"], "summary": "latest evaluation summary", "value_json": _csv_value(logs["latest_evaluation_summary"])})
    return rows


def _write_log_csv(path: Path, rows: list[dict[str, Any]], *, encoding: str) -> Path:
    with path.open("w", newline="", encoding=encoding) as f:
        writer = csv.DictWriter(f, fieldnames=LOG_CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def export_participant_logs_csv(db: Session, participant_id: str) -> Path:
    logs = participant_logs(db, participant_id)
    participant = logs["participant"]
    path = Path(get_settings().export_dir) / f"{participant['display_code']}_logs.csv"
    rows = _log_csv_rows_from_participant_logs(logs)
    return _write_log_csv(path, rows, encoding="utf-8")


def export_participant_logs_excel_csv(db: Session, participant_id: str) -> Path:
    logs = participant_logs(db, participant_id)
    participant = logs["participant"]
    path = Path(get_settings().export_dir) / f"{participant['display_code']}_logs_excel.csv"
    rows = _log_csv_rows_from_participant_logs(logs)
    return _write_log_csv(path, rows, encoding="utf-8-sig")


def export_overview_logs_csv(db: Session) -> Path:
    path = Path(get_settings().export_dir) / "overview.csv"
    rows: list[dict[str, Any]] = []
    for participant in db.query(Participant).order_by(Participant.created_at).all():
        rows.extend(_log_csv_rows_from_participant_logs(participant_logs(db, participant.id)))
    return _write_log_csv(path, rows, encoding="utf-8")


def export_overview_logs_excel_csv(db: Session) -> Path:
    path = Path(get_settings().export_dir) / "overview_excel.csv"
    rows: list[dict[str, Any]] = []
    for participant in db.query(Participant).order_by(Participant.created_at).all():
        rows.extend(_log_csv_rows_from_participant_logs(participant_logs(db, participant.id)))
    return _write_log_csv(path, rows, encoding="utf-8-sig")


def export_csv(db: Session, name: str) -> Path:
    if name not in EXPORTS:
        raise HTTPException(status_code=404, detail="unknown export")
    model, columns = EXPORTS[name]
    path = Path(get_settings().export_dir) / f"{name}.csv"
    rows = db.query(model).all()
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: getattr(row, col) for col in columns})
    db.add(ExportJob(export_name=name, file_path=str(path), status="success", row_count=len(rows)))
    db.commit()
    return path
