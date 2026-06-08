from __future__ import annotations

import csv
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ai.codex_app_server_backend import CodexAppServerError
from app.ai.backend import lower_level, raise_level, strategy_for
from app.ai.factory import get_ai_backend
from app.core.config import get_settings
from app.models import (
    AICallLog,
    Attempt,
    ConceptUnderstandingAttempt,
    EvaluationSummary,
    ExportJob,
    LearnerState,
    LearningSession,
    Participant,
    ParticipantSurvey,
    PrerequisiteTerm,
    Question,
    QuestionDisplayOrder,
    QuestionOption,
    RecurrenceEvent,
    Term,
    TermAssignment,
    TermUnderstandingAttempt,
    TutorSession,
    TutorTurn,
    now,
)
from app.rag import retrieve_rag_context


PUBLIC_LEVEL = {"L3": "しっかり確認", "L2": "観点を確認", "L1": "自分で整理", "L0": "ヒントなし"}
TERM_ATTEMPT_LIMIT = 2
CONCEPT_ATTEMPT_LIMIT = 4


def _rag_query(*parts: object) -> str:
    return " ".join(str(part) for part in parts if part)


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


def save_survey(db: Session, participant_id: str, payload: dict[str, Any]) -> None:
    participant = get_participant(db, participant_id)
    phase = payload.get("phase", "post_survey")
    survey = ParticipantSurvey(
        participant_id=participant_id,
        phase=phase,
        ai_experience_level=payload.get("ai_experience_level"),
        programming_experience_level=payload.get("programming_experience_level"),
        llm_usage_level=payload.get("llm_usage_level"),
        self_rated_ai_knowledge=payload.get("self_rated_ai_knowledge"),
        term_confidences=payload.get("term_confidences"),
        usability_rating=payload.get("usability_rating"),
        helpfulness_rating=payload.get("helpfulness_rating"),
        perceived_hint_amount=payload.get("perceived_hint_amount"),
        free_comment=payload.get("free_comment"),
    )
    db.add(survey)
    participant.current_step = "finish" if phase == "post_survey" else "pretest"
    if phase == "post_survey":
        participant.completed_at = now()
    db.commit()


def _question_query_for_phase(db: Session, participant: Participant, phase: str):
    query = db.query(Question).join(Term, Question.term_id == Term.id).filter(Question.phase == phase, Question.is_active.is_(True), Term.is_active.is_(True))
    if phase in {"l0_check", "transfer"}:
        return query.filter(Question.id == "__disabled_current_flow__")
    if phase in {"retest", "l0_check", "transfer"}:
        target_term_ids = [
            row.term_id
            for row in db.query(TermAssignment)
            .filter(TermAssignment.participant_id == participant.id, TermAssignment.is_learning_target.is_(True))
            .all()
        ]
        if target_term_ids:
            query = query.filter(Question.term_id.in_(target_term_ids))
    return query.order_by(Term.display_order, Question.variant_key)


def question_payloads(db: Session, participant_id: str, phase: str) -> list[dict[str, Any]]:
    participant = get_participant(db, participant_id)
    questions = _question_query_for_phase(db, participant, phase).all()
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
                "body": question.body,
                "question_type": question.question_type,
                "options": public_options,
                "requires_reason": phase not in {"pretest", "retest"},
                "requires_confidence": False,
            }
        )
    return out


def submit_attempt(db: Session, payload: dict[str, Any], idempotency_key: str | None = None) -> Attempt:
    question = db.get(Question, payload["question_id"])
    if not question:
        raise HTTPException(status_code=404, detail="question not found")
    participant = get_participant(db, payload["participant_id"])
    if idempotency_key:
        existing = db.query(Attempt).filter_by(participant_id=participant.id, idempotency_key=idempotency_key).one_or_none()
        if existing:
            return existing
    attempt = Attempt(
        participant_id=participant.id,
        term_id=question.term_id,
        question_id=question.id,
        phase=payload.get("phase") or question.phase,
        selected_option_id=payload.get("selected_option_id"),
        free_text_answer=payload.get("free_text_answer"),
        reason_text=payload.get("reason_text"),
        confidence=payload.get("confidence"),
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
    return {
        "participant_id": participant.id,
        "group_condition": participant.group_condition,
        "term": {"slug": term.slug, "label": term.label, "definition": term.description},
        "question": {"id": question.id, "phase": question.phase, "question_type": question.question_type, "body": question.body, "expected_answer": question.expected_answer},
        "selected_option": None
        if not option
        else {"id": option.id, "body": option.body, "is_correct": option.is_correct, "initial_misconception_type": option.misconception_type},
        "learner_response": {"reason_text": attempt.reason_text, "free_text_answer": attempt.free_text_answer, "confidence": attempt.confidence},
        "history": {"previous_attempts": []},
    }


def _priority(attempt: Attempt) -> tuple[float, str]:
    if attempt.diagnosed_status == "misconception":
        score = 70
        if attempt.misconception_type in {"M1", "M2"}:
            score += 20
        elif attempt.misconception_type == "M3":
            score += 10
        return score, f"{attempt.misconception_type}を重点確認"
    if attempt.diagnosed_status == "unknown":
        return 55, "基礎理解を確認"
    if attempt.diagnosed_status == "unstable_correct":
        return 45, "理由説明を確認"
    return 10, "転移準備"


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
    attempt_by_term_id = {attempt.term_id: attempt for attempt in scored_attempts}
    for assignment in assignments:
        attempt = attempt_by_term_id.get(assignment.term_id)
        assignment.is_learning_target = bool(attempt and attempt.diagnosed_status != "stable_correct")
    participant.current_step = "learning_targets"
    db.commit()
    return sum(1 for assignment in assignments if assignment.is_learning_target)


def learning_targets(db: Session, participant_id: str) -> list[dict[str, Any]]:
    participant = get_participant(db, participant_id)
    terminal_term_ids = {
        session.term_id
        for session in db.query(LearningSession)
        .filter(
            LearningSession.participant_id == participant.id,
            LearningSession.status.in_(("completed", "blocked", "failed")),
        )
        .all()
    }
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
            "summary_for_learner": state.state_summary or "この用語を重点的に確認します。",
            "current_scaffolding_level_for_display": PUBLIC_LEVEL.get(state.scaffolding_level, "確認"),
            "learning_mode": "proposed_gate" if participant.group_condition == "proposed" else "control_general",
        }
        for _, term, state in rows
        if term.id not in terminal_term_ids
    ]


def _term_by_slug(db: Session, term_slug: str) -> Term:
    term = db.query(Term).filter_by(slug=term_slug, is_active=True).one_or_none()
    if not term:
        raise HTTPException(status_code=404, detail="term not found")
    return term


def _pretest_attempt_for_term(db: Session, participant_id: str, term_id: str) -> Attempt | None:
    return (
        db.query(Attempt)
        .filter_by(participant_id=participant_id, term_id=term_id, phase="pretest")
        .order_by(Attempt.created_at.desc())
        .first()
    )


def _pretest_context(db: Session, participant: Participant, term: Term) -> dict[str, Any]:
    attempt = _pretest_attempt_for_term(db, participant.id, term.id)
    option = _selected_option(db, attempt) if attempt else None
    state = db.query(LearnerState).filter_by(participant_id=participant.id, term_id=term.id).one_or_none()
    assignment = db.query(TermAssignment).filter_by(participant_id=participant.id, term_id=term.id).one_or_none()
    return {
        "pretest_diagnosis": None
        if not state
        else {
            "diagnosed_status": state.current_status,
            "misconception_type": state.primary_misconception,
            "natural_language_diagnosis": state.state_summary,
        },
        "selected_option_body": option.body if option else None,
        "selection_reason": assignment.selection_reason if assignment else None,
    }


def _learning_rag_context(term: Term, *parts: object) -> dict[str, Any]:
    return retrieve_rag_context(_rag_query(term.label, term.description, *parts))


def _prerequisite_rows(db: Session, session_id: str) -> list[PrerequisiteTerm]:
    return (
        db.query(PrerequisiteTerm)
        .filter_by(learning_session_id=session_id)
        .order_by(PrerequisiteTerm.display_order)
        .all()
    )


def _public_prerequisite(row: PrerequisiteTerm) -> dict[str, Any]:
    return {
        "prerequisite_id": row.id,
        "term_label": row.term_label,
        "material": row.material,
        "check_question": row.check_question,
        "display_order": row.display_order,
        "status": row.status,
        "attempt_count": row.attempt_count,
        "max_attempts": TERM_ATTEMPT_LIMIT,
        "last_feedback": row.last_feedback,
        "remediation_material": row.remediation_material,
    }


async def create_learning_session(db: Session, participant_id: str, term_slug: str) -> LearningSession:
    participant = get_participant(db, participant_id)
    term = _term_by_slug(db, term_slug)
    existing = (
        db.query(LearningSession)
        .filter_by(participant_id=participant.id, term_id=term.id)
        .order_by(LearningSession.created_at.desc())
        .first()
    )
    if existing:
        return existing

    count = db.query(func.count(LearningSession.id)).filter_by(participant_id=participant.id, term_id=term.id).scalar() or 0
    status = "term_understanding" if participant.group_condition == "proposed" else "control_learning"
    session = LearningSession(
        participant_id=participant.id,
        term_id=term.id,
        group_condition=participant.group_condition,
        session_index=count + 1,
        status=status,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    if participant.group_condition == "proposed":
        context = _pretest_context(db, participant, term)
        payload = {
            "participant_id": participant.id,
            "group_condition": participant.group_condition,
            "target_term": {"slug": term.slug, "label": term.label, "description": term.description},
            **context,
            "rag_context": _learning_rag_context(term, context.get("selected_option_body"), context.get("selection_reason")),
        }
        result = await _ai_call(db, "generate_prerequisite_plan", payload)
        prerequisites = result.get("prerequisites") or []
        for index, item in enumerate(prerequisites[:3], start=1):
            db.add(
                PrerequisiteTerm(
                    learning_session_id=session.id,
                    term_label=item["term_label"],
                    material=item["material"],
                    check_question=item["check_question"],
                    expected_answer=item["expected_answer"],
                    display_order=index,
                )
            )
        db.commit()
    return session


def learning_session_state(db: Session, session_id: str) -> dict[str, Any]:
    session = db.get(LearningSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="learning session not found")
    participant = get_participant(db, session.participant_id)
    term = db.get(Term, session.term_id)
    prerequisites = _prerequisite_rows(db, session.id)
    current = next((row for row in prerequisites if row.status != "passed"), None)
    return {
        "learning_session_id": session.id,
        "participant_id": participant.id,
        "group_condition": participant.group_condition,
        "status": session.status,
        "term_slug": term.slug,
        "term_label": term.label,
        "term_description": term.description,
        "prerequisites": [_public_prerequisite(row) for row in prerequisites],
        "current_prerequisite_id": current.id if current else None,
        "concept": {
            "material": session.concept_material,
            "prompt": session.concept_prompt,
            "attempt_count": session.concept_attempt_count,
            "max_attempts": CONCEPT_ATTEMPT_LIMIT,
        }
        if session.concept_material or session.status == "concept_understanding"
        else None,
        "limits": {"term_max_attempts": TERM_ATTEMPT_LIMIT, "concept_max_attempts": CONCEPT_ATTEMPT_LIMIT},
        "last_feedback": session.last_feedback,
        "blocked_reason": session.blocked_reason,
    }


async def _ensure_concept_material(db: Session, session: LearningSession) -> None:
    if session.concept_material:
        session.status = "concept_understanding"
        db.commit()
        return
    term = db.get(Term, session.term_id)
    participant = get_participant(db, session.participant_id)
    prereqs = _prerequisite_rows(db, session.id)
    context = _pretest_context(db, participant, term)
    payload = {
        "participant_id": participant.id,
        "group_condition": participant.group_condition,
        "target_term": {"slug": term.slug, "label": term.label, "description": term.description},
        "prerequisites": [
            {"term_label": row.term_label, "material": row.material, "expected_answer": row.expected_answer}
            for row in prereqs
        ],
        **context,
        "rag_context": _learning_rag_context(term, *[row.term_label for row in prereqs]),
    }
    result = await _ai_call(db, "generate_concept_material", payload)
    session.concept_material = result["concept_material"]
    session.concept_prompt = result["concept_prompt"]
    session.concept_expected_answer = result["expected_answer"]
    session.status = "concept_understanding"
    db.commit()


async def submit_prerequisite_attempt(db: Session, session_id: str, prerequisite_id: str, learner_answer: str) -> dict[str, Any]:
    session = db.get(LearningSession, session_id)
    prereq = db.get(PrerequisiteTerm, prerequisite_id)
    if not session or not prereq or prereq.learning_session_id != session_id:
        raise HTTPException(status_code=404, detail="prerequisite not found")
    if session.group_condition != "proposed":
        raise HTTPException(status_code=400, detail="not a proposed learning session")
    if session.status in {"blocked", "failed", "completed"}:
        raise HTTPException(status_code=400, detail=f"session is {session.status}")

    participant = get_participant(db, session.participant_id)
    term = db.get(Term, session.term_id)
    attempt_index = prereq.attempt_count + 1
    payload = {
        "participant_id": participant.id,
        "group_condition": participant.group_condition,
        "target_term": {"slug": term.slug, "label": term.label, "description": term.description},
        "prerequisite": {
            "term_label": prereq.term_label,
            "material": prereq.material,
            "check_question": prereq.check_question,
            "expected_answer": prereq.expected_answer,
        },
        "learner_answer": learner_answer,
        "attempt_index": attempt_index,
        "max_attempts": TERM_ATTEMPT_LIMIT,
        **_pretest_context(db, participant, term),
        "rag_context": _learning_rag_context(term, prereq.term_label, learner_answer),
    }
    result = await _ai_call(db, "grade_prerequisite_answer", payload)
    is_passed = bool(result["is_passed"])
    db.add(
        TermUnderstandingAttempt(
            prerequisite_term_id=prereq.id,
            participant_id=participant.id,
            learning_session_id=session.id,
            attempt_index=attempt_index,
            learner_answer=learner_answer,
            is_passed=is_passed,
            score=result.get("score"),
            feedback=result["feedback"],
            remediation_material=result.get("remediation_material"),
            grading_json=result,
        )
    )
    prereq.attempt_count = attempt_index
    prereq.last_feedback = result["feedback"]
    prereq.remediation_material = result.get("remediation_material")
    prereq.status = "passed" if is_passed else ("failed" if attempt_index >= TERM_ATTEMPT_LIMIT else "review")
    session.last_feedback = result["feedback"]

    if not is_passed and attempt_index >= TERM_ATTEMPT_LIMIT:
        session.status = "blocked"
        session.blocked_reason = f"{prereq.term_label} の理解確認を2回通過できませんでした。"
        session.completed_at = now()
    elif all(row.status == "passed" for row in _prerequisite_rows(db, session.id) if row.id != prereq.id) and is_passed:
        session.term_pass_count = len(_prerequisite_rows(db, session.id))
        await _ensure_concept_material(db, session)
    else:
        session.status = "term_understanding"
    db.commit()
    return {"is_passed": is_passed, "feedback": result["feedback"], "session": learning_session_state(db, session.id)}


def _ids_for_labels(prereqs: list[PrerequisiteTerm], labels: list[str]) -> list[str]:
    out: list[str] = []
    for label in labels:
        for row in prereqs:
            if row.term_label == label and row.id not in out:
                out.append(row.id)
                break
    return out


async def submit_concept_attempt(db: Session, session_id: str, learner_answer: str) -> dict[str, Any]:
    session = db.get(LearningSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="learning session not found")
    if session.group_condition != "proposed":
        raise HTTPException(status_code=400, detail="not a proposed learning session")
    if session.status in {"blocked", "failed", "completed"}:
        raise HTTPException(status_code=400, detail=f"session is {session.status}")
    prereqs = _prerequisite_rows(db, session.id)
    if not prereqs or any(row.status != "passed" for row in prereqs):
        raise HTTPException(status_code=400, detail="all prerequisites must pass first")
    await _ensure_concept_material(db, session)

    participant = get_participant(db, session.participant_id)
    term = db.get(Term, session.term_id)
    attempt_index = session.concept_attempt_count + 1
    payload = {
        "participant_id": participant.id,
        "group_condition": participant.group_condition,
        "target_term": {"slug": term.slug, "label": term.label, "description": term.description},
        "prerequisites": [
            {"term_label": row.term_label, "material": row.material, "expected_answer": row.expected_answer}
            for row in prereqs
        ],
        "concept_material": session.concept_material,
        "concept_prompt": session.concept_prompt,
        "expected_answer": session.concept_expected_answer,
        "learner_answer": learner_answer,
        "attempt_index": attempt_index,
        "max_attempts": CONCEPT_ATTEMPT_LIMIT,
        **_pretest_context(db, participant, term),
        "rag_context": _learning_rag_context(term, session.concept_prompt, learner_answer),
    }
    result = await _ai_call(db, "grade_concept_answer", payload)
    missing_ids = _ids_for_labels(prereqs, result.get("missing_prerequisite_labels") or [])
    review_ids = _ids_for_labels(prereqs, result.get("review_prerequisite_labels") or [])
    for prereq_id in missing_ids + review_ids:
        row = db.get(PrerequisiteTerm, prereq_id)
        if row:
            row.status = "review"
            row.attempt_count = 0
    is_passed = bool(result["is_passed"])
    db.add(
        ConceptUnderstandingAttempt(
            learning_session_id=session.id,
            participant_id=participant.id,
            attempt_index=attempt_index,
            concept_material=session.concept_material or "",
            prompt=session.concept_prompt or "",
            learner_answer=learner_answer,
            is_passed=is_passed,
            score=result.get("score"),
            feedback=result["feedback"],
            missing_prerequisite_ids=missing_ids,
            review_prerequisite_ids=review_ids,
            grading_json=result,
        )
    )
    session.concept_attempt_count = attempt_index
    session.last_feedback = result["feedback"]
    if is_passed:
        session.status = "completed"
        session.completed_at = now()
    elif attempt_index >= CONCEPT_ATTEMPT_LIMIT:
        session.status = "failed"
        session.blocked_reason = "概念理解確認を4回通過できませんでした。"
        session.completed_at = now()
    else:
        session.status = "term_understanding" if (missing_ids or review_ids) else "concept_understanding"
    db.commit()
    return {
        "is_passed": is_passed,
        "feedback": result["feedback"],
        "missing_prerequisite_ids": missing_ids,
        "review_prerequisite_ids": review_ids,
        "session": learning_session_state(db, session.id),
    }


async def generate_control_learning_turn(db: Session, session_id: str) -> dict[str, Any]:
    session = db.get(LearningSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="learning session not found")
    if session.group_condition != "control":
        raise HTTPException(status_code=400, detail="not a control learning session")
    participant = get_participant(db, session.participant_id)
    term = db.get(Term, session.term_id)
    payload = {
        "participant_id": participant.id,
        "group_condition": "control",
        "target_term": {"slug": term.slug, "label": term.label, "description": term.description},
        "rag_context": _learning_rag_context(term),
    }
    result = await _ai_call(db, "generate_control_learning_turn", payload)
    tutor_count = db.query(func.count(TutorSession.id)).filter_by(participant_id=participant.id, term_id=term.id).scalar() or 0
    tutor_session = TutorSession(participant_id=participant.id, term_id=term.id, session_index=tutor_count + 1, group_condition="control")
    db.add(tutor_session)
    db.flush()
    turn = TutorTurn(
        tutor_session_id=tutor_session.id,
        turn_index=1,
        scaffolding_level=None,
        teaching_strategy="general_explanation",
        strategy_changed=False,
        tutor_message=result["tutor_message"],
        learner_prompt=result["learner_prompt"],
        practice_question_json=result["practice_question"],
        forbidden_help_given=result["forbidden_help_given"],
    )
    db.add(turn)
    db.commit()
    db.refresh(turn)
    return {
        "turn_id": turn.id,
        "tutor_message": turn.tutor_message,
        "learner_prompt": turn.learner_prompt,
        "practice_question": turn.practice_question_json,
        "requires_learner_response": True,
    }


async def respond_control_learning_answer(db: Session, session_id: str, turn_id: str, learner_response: str) -> dict[str, Any]:
    session = db.get(LearningSession, session_id)
    turn = db.get(TutorTurn, turn_id)
    if not session or not turn:
        raise HTTPException(status_code=404, detail="control turn not found")
    if session.group_condition != "control":
        raise HTTPException(status_code=400, detail="not a control learning session")
    participant = get_participant(db, session.participant_id)
    term = db.get(Term, session.term_id)
    payload = {
        "participant_id": participant.id,
        "group_condition": "control",
        "target_term": {"slug": term.slug, "label": term.label, "description": term.description},
        "tutor_turn": {
            "tutor_message": turn.tutor_message,
            "learner_prompt": turn.learner_prompt,
            "practice_question": turn.practice_question_json,
        },
        "learner_response": learner_response,
        "rag_context": _learning_rag_context(term, learner_response),
    }
    result = await _ai_call(db, "grade_control_learning_answer", payload)
    turn.learner_response = learner_response
    turn.ai_feedback = result["feedback"]
    turn.forbidden_help_given = bool(result["forbidden_help_given"])
    session.status = "completed" if result["is_complete"] else "control_learning"
    session.completed_at = now() if result["is_complete"] else None
    session.last_feedback = result["feedback"]
    db.commit()
    return {"feedback": result["feedback"], "session_completed": result["is_complete"], "session": learning_session_state(db, session.id)}


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
    turn_count = db.query(func.count(TutorTurn.id)).filter_by(tutor_session_id=session.id).scalar() or 0
    if turn_count >= get_settings().max_turns_per_term:
        raise HTTPException(status_code=400, detail="max turns reached")
    payload = {
        "participant_id": participant.id,
        "group_condition": participant.group_condition,
        "term": {"slug": term.slug, "label": term.label, "description": term.description},
        "learner_state": {
            "current_status": state.current_status,
            "primary_misconception": state.primary_misconception,
            "scaffolding_level": state.scaffolding_level,
            "teaching_strategy": state.teaching_strategy,
            "recurrence_count": state.recurrence_count,
        },
        "previous_answer": previous_attempt.reason_text if previous_attempt else "",
        "previous_diagnosis_for_learner": state.state_summary,
    }
    payload["rag_context"] = retrieve_rag_context(
        _rag_query(
            term.label,
            term.description,
            state.current_status,
            state.primary_misconception,
            state.teaching_strategy,
            state.state_summary,
        )
    )
    result = await _ai_call(db, "generate_tutoring_turn", payload)
    turn = TutorTurn(
        tutor_session_id=session.id,
        turn_index=turn_count + 1,
        scaffolding_level=result["scaffolding_level"],
        teaching_strategy=result["teaching_strategy"],
        previous_teaching_strategy=state.previous_teaching_strategy,
        strategy_changed=False,
        tutor_message=result["tutor_message"],
        learner_prompt=result["learner_prompt"],
        practice_question_json=result["practice_question"],
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
    feedback_payload = {
        "participant_id": participant.id,
        "group_condition": participant.group_condition,
        "term": {"slug": term.slug, "label": term.label, "description": term.description},
        "learner_state": {
            "current_status": state.current_status,
            "primary_misconception": state.primary_misconception if participant.group_condition == "proposed" else None,
            "scaffolding_level": state.scaffolding_level,
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
    }
    feedback_payload["rag_context"] = retrieve_rag_context(
        _rag_query(
            term.label,
            term.description,
            state.current_status,
            state.primary_misconception,
            state.teaching_strategy,
            turn.learner_prompt,
            turn.practice_question_json,
            response,
        )
    )
    result = await _ai_call(db, "generate_feedback", feedback_payload)
    correct = result["next_action"] == "move_next"
    next_level = result["next_scaffolding_level"] if result.get("next_scaffolding_level") else (lower_level(state.scaffolding_level) if correct else state.scaffolding_level)
    turn.learner_response = response
    turn.learner_confidence = None
    turn.next_scaffolding_level = next_level
    turn.ai_feedback = result["feedback"]
    state.scaffolding_level = next_level
    state.stable_correct_count += 1 if correct else 0
    state.current_status = "stable_correct" if correct else state.current_status
    state.updated_reason = result["state_update_reason"]
    state.last_tutor_turn_id = turn.id
    db.commit()
    return {"feedback": turn.ai_feedback, "next_action": result["next_action"], "session_completed": turn.turn_index >= get_settings().max_turns_per_term or correct}


async def score_phase(db: Session, participant_id: str, phase: str) -> dict[str, Any]:
    participant = get_participant(db, participant_id)
    attempts = db.query(Attempt).filter_by(participant_id=participant.id, phase=phase).all()
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
        result = await _ai_call(db, "grade_response", payload)
        attempt.is_correct = result["is_correct"]
        attempt.score = result["score"]
        attempt.diagnosed_status = result["diagnosed_status"]
        attempt.misconception_type = result["misconception_type"]
        attempt.secondary_misconception_type = result["secondary_misconception_type"]
        attempt.l0_success = result["l0_success"]
        attempt.transfer_success = result["transfer_success"]
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
        if phase == "l0_check":
            state.l0_success_count += 1 if attempt.is_correct else 0
            state.scaffolding_level = "L0" if attempt.is_correct else raise_level("L0")
        if phase == "transfer":
            state.transfer_success_count += 1 if attempt.is_correct else 0
            if not attempt.is_correct:
                attempt.misconception_type = "M4"
        state.current_status = "stable_correct" if attempt.is_correct else "misconception"
        state.last_attempt_id = attempt.id
    participant.current_step = {"retest": "post_survey", "l0_check": "post_survey", "transfer": "post_survey"}.get(phase, participant.current_step)
    db.commit()
    return {"status": "completed", "next_step": participant.current_step}


def _rate(items: list[Attempt], predicate) -> float | None:
    if not items:
        return None
    return sum(1 for item in items if predicate(item)) / len(items)


def recalculate_evaluation(db: Session, participant_id: str) -> EvaluationSummary:
    participant = get_participant(db, participant_id)
    attempts = db.query(Attempt).filter_by(participant_id=participant.id).all()
    by_phase = {phase: [a for a in attempts if a.phase == phase] for phase in ["pretest", "retest", "l0_check", "transfer"]}
    initial_m = [a for a in by_phase["pretest"] if a.misconception_type in {"M1", "M2", "M3"}]
    same_rec = [a for a in by_phase["retest"] if a.recurrence_flag]
    def m_rate(m: str) -> float | None:
        denom = [a for a in initial_m if a.misconception_type == m]
        if not denom:
            return None
        rec_terms = {a.term_id for a in by_phase["retest"] if a.recurrence_flag and a.misconception_type == m}
        return len(rec_terms) / len(denom)

    learning_sessions = db.query(LearningSession).filter_by(participant_id=participant.id).all()
    session_ids = [session.id for session in learning_sessions]
    prerequisites = db.query(PrerequisiteTerm).filter(PrerequisiteTerm.learning_session_id.in_(session_ids)).all() if session_ids else []
    proposed_sessions = [session for session in learning_sessions if session.group_condition == "proposed"]
    completed_proposed = [session for session in proposed_sessions if session.status == "completed"]

    summary = EvaluationSummary(
        participant_id=participant.id,
        group_condition=participant.group_condition,
        pretest_score=_rate(by_phase["pretest"], lambda a: bool(a.is_correct)),
        retest_score=_rate(by_phase["retest"], lambda a: bool(a.is_correct)),
        l0_correct_rate=_rate(by_phase["l0_check"], lambda a: bool(a.l0_success)),
        transfer_correct_rate=_rate(by_phase["transfer"], lambda a: bool(a.transfer_success)),
        same_misconception_recurrence_rate=(len(same_rec) / len(initial_m)) if initial_m else None,
        m1_recurrence_rate=m_rate("M1"),
        m2_recurrence_rate=m_rate("M2"),
        m3_recurrence_rate=m_rate("M3"),
        m4_failure_rate=_rate(by_phase["transfer"], lambda a: a.misconception_type == "M4"),
        unknown_persistence_rate=None,
        prerequisite_pass_rate=_rate(prerequisites, lambda p: p.status == "passed"),
        concept_pass_rate=(len(completed_proposed) / len(proposed_sessions)) if proposed_sessions else None,
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
                "pretest_score": avg("pretest_score"),
                "retest_score": avg("retest_score"),
                "same_misconception_recurrence_rate": avg("same_misconception_recurrence_rate"),
                "l0_correct_rate": avg("l0_correct_rate"),
                "transfer_correct_rate": avg("transfer_correct_rate"),
                "prerequisite_pass_rate": avg("prerequisite_pass_rate"),
                "concept_pass_rate": avg("concept_pass_rate"),
            }
        )
    return {"groups": rows}


EXPORTS = {
    "participants": (Participant, ["id", "display_code", "group_condition", "assignment_method", "current_step", "started_at", "completed_at"]),
    "participant_surveys": (ParticipantSurvey, ["id", "participant_id", "phase", "ai_experience_level", "programming_experience_level", "llm_usage_level", "self_rated_ai_knowledge", "term_confidences", "free_comment"]),
    "attempts": (Attempt, ["id", "participant_id", "term_id", "phase", "question_id", "selected_option_id", "reason_text", "free_text_answer", "confidence", "is_correct", "score", "diagnosed_status", "misconception_type", "recurrence_flag", "l0_success", "transfer_success", "requires_manual_review", "created_at"]),
    "learner_states": (LearnerState, ["participant_id", "term_id", "current_status", "primary_misconception", "scaffolding_level", "teaching_strategy", "stable_correct_count", "recurrence_count", "l0_success_count", "transfer_success_count", "updated_at"]),
    "learning_sessions": (LearningSession, ["id", "participant_id", "term_id", "group_condition", "session_index", "status", "term_pass_count", "concept_attempt_count", "blocked_reason", "completed_at", "created_at"]),
    "prerequisite_terms": (PrerequisiteTerm, ["id", "learning_session_id", "term_label", "display_order", "status", "attempt_count", "last_feedback", "created_at"]),
    "term_understanding_attempts": (TermUnderstandingAttempt, ["id", "prerequisite_term_id", "participant_id", "learning_session_id", "attempt_index", "learner_answer", "is_passed", "score", "feedback", "created_at"]),
    "concept_understanding_attempts": (ConceptUnderstandingAttempt, ["id", "learning_session_id", "participant_id", "attempt_index", "learner_answer", "is_passed", "score", "feedback", "missing_prerequisite_ids", "review_prerequisite_ids", "created_at"]),
    "tutor_sessions": (TutorSession, ["id", "participant_id", "term_id", "session_index", "group_condition", "started_at", "ended_at"]),
    "tutor_turns": (TutorTurn, ["id", "tutor_session_id", "turn_index", "scaffolding_level", "teaching_strategy", "strategy_changed", "tutor_message", "learner_response", "ai_feedback", "next_scaffolding_level", "forbidden_help_given", "created_at"]),
    "recurrence_events": (RecurrenceEvent, ["id", "participant_id", "term_id", "previous_attempt_id", "current_attempt_id", "previous_misconception_type", "current_misconception_type", "is_same_type", "phase", "created_at"]),
    "ai_call_logs": (AICallLog, ["id", "provider", "fallback_provider", "purpose", "status", "error_code", "latency_ms", "created_at"]),
    "evaluation_summary": (EvaluationSummary, ["participant_id", "group_condition", "pretest_score", "retest_score", "l0_correct_rate", "transfer_correct_rate", "same_misconception_recurrence_rate", "m1_recurrence_rate", "m2_recurrence_rate", "m3_recurrence_rate", "m4_failure_rate", "prerequisite_pass_rate", "concept_pass_rate", "learning_target_count", "completed", "created_at"]),
}


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
