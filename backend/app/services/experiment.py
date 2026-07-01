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
from app.ai.backend import initial_level, lower_level, raise_level, strategy_for
from app.ai.factory import get_ai_backend
from app.core.config import get_settings
from app.models import (
    AdaptiveSupportEvent,
    AICallLog,
    Attempt,
    AuditEvent,
    ConceptUnderstandingAttempt,
    ContentVersion,
    EvaluationSummary,
    ExportJob,
    GeneratedLearningMaterial,
    LearnerState,
    LearningChoiceAttempt,
    LearningQuestion,
    LearningQuestionDisplayOrder,
    LearningQuestionOption,
    LearningQuestionSlot,
    LearningSession,
    LearningSessionPrerequisite,
    MisconceptionObservation,
    Participant,
    ParticipantSurvey,
    PrerequisiteTerm,
    PrerequisiteDefinition,
    Question,
    QuestionDisplayOrder,
    QuestionOption,
    RecurrenceEvent,
    RetestCycle,
    RetestCycleResult,
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
CONTROL_TERM_ATTEMPT_LIMIT = 1
PHASE1_ATTEMPT_LIMIT = 3
PHASE2_ATTEMPT_LIMIT = 3
CONCEPT_ATTEMPT_LIMIT = PHASE1_ATTEMPT_LIMIT
TERMINAL_LEARNING_STATUSES = {"completed", "blocked", "failed", "failed_phase1", "failed_phase2"}
ALLOWED_ADAPTIVE_STRATEGIES = {
    "category_reorientation",
    "boundary_comparison",
    "deep_structure_focus",
    "foundational_explanation",
    "diagnostic_clarification",
    "fading",
    "self_explanation_check",
}


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
    active_content = (
        db.query(ContentVersion)
        .filter_by(content_type="experiment_release", is_active=True)
        .order_by(ContentVersion.imported_at.desc())
        .first()
    )
    participant = Participant(
        display_code=next_display_code(db),
        group_condition=group_condition,
        assignment_method=assignment_method,
        consent_checked=consent_checked,
        content_version_id=active_content.id if active_content else None,
        current_step="initial_test",
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
    participant.current_step = "finish" if phase == "post_survey" else "initial_test"
    if phase == "post_survey":
        participant.completed_at = now()
    db.commit()


def _question_query_for_phase(db: Session, participant: Participant, phase: str):
    query = db.query(Question).join(Term, Question.term_id == Term.id).filter(
        Question.phase == phase,
        Term.is_active.is_(True),
    )
    if participant.content_version_id and phase in {"initial_test", "retest", "final_test"}:
        query = query.filter(Question.content_version_id == participant.content_version_id)
    else:
        query = query.filter(Question.is_active.is_(True))
    if phase in {"l0_check", "transfer"}:
        return query.filter(Question.id == "__disabled_current_flow__")
    if phase in {"l0_check", "transfer"}:
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
    if not participant.content_version_id and phase in {"initial_test", "retest", "final_test"}:
        release = (
            db.query(ContentVersion)
            .filter_by(content_type="experiment_release", is_active=True)
            .order_by(ContentVersion.imported_at.desc())
            .first()
        )
        if release:
            participant.content_version_id = release.id
            db.commit()
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
                "requires_reason": phase not in {"initial_test", "retest", "final_test"},
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
        log = AICallLog(
                provider=backend.provider,
                fallback_provider=result.pop("_fallback_provider", None),
                purpose=purpose,
                request_payload=payload,
                response_payload=result,
                status="success",
                latency_ms=latency,
            )
        db.add(log)
        db.commit()
        db.refresh(log)
        return {**result, "_ai_call_log_id": log.id}
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


async def diagnose_initial_test(db: Session, participant_id: str) -> int:
    participant = get_participant(db, participant_id)
    attempts = db.query(Attempt).filter_by(participant_id=participant.id, phase="initial_test").all()
    if not attempts:
        raise HTTPException(status_code=400, detail="initial_test attempts not found")

    scored_attempts: list[Attempt] = []
    for attempt in attempts:
        option = _selected_option(db, attempt)
        if not option:
            raise HTTPException(status_code=400, detail="pretest requires a selected option")
        if option.is_correct:
            status, misconception, natural = "stable_correct", None, "この概念を正しく弁別できています。"
        elif option.misconception_type == "unknown":
            status, misconception, natural = "unknown", "unknown", "まず基本的な意味から確認します。"
        else:
            status, misconception = "misconception", option.misconception_type
            natural = {
                "M1": "概念を別の種類のものとして捉えている可能性があります。",
                "M2": "似ている概念との違いを確認します。",
                "M3": "言葉の表面ではなく、仕組みに注目して確認します。",
            }.get(misconception, "この概念を重点的に確認します。")
        result = {
            "is_correct": option.is_correct,
            "diagnosed_status": status,
            "misconception_type": misconception,
            "secondary_misconception_type": None,
            "diagnosis_confidence": 1.0,
            "natural_language_diagnosis": natural,
            "evidence": option.body,
            "recommended_initial_scaffolding_level": initial_level(status, misconception, None),
            "recommended_teaching_strategy": strategy_for(misconception, status, participant.group_condition),
            "requires_manual_review": False,
        }
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
            db.flush()
        existing_observation = db.query(MisconceptionObservation).filter_by(
            source_phase="initial_test",
            source_attempt_id=attempt.id,
        ).one_or_none()
        if not existing_observation:
            observation = MisconceptionObservation(
                participant_id=participant.id,
                term_id=attempt.term_id,
                source_phase="initial_test",
                source_attempt_type="test",
                source_attempt_id=attempt.id,
                diagnosed_status=result["diagnosed_status"],
                primary_misconception_type=result["misconception_type"],
                secondary_misconception_type=result["secondary_misconception_type"],
                diagnosis_confidence=result["diagnosis_confidence"],
                diagnosis_evidence=result.get("evidence"),
                resolution_stage="none",
                transition_type="initial",
                standard_strategy=result["recommended_teaching_strategy"],
                applied_strategy=result["recommended_teaching_strategy"],
                requires_manual_review=result["requires_manual_review"],
            )
            db.add(observation)
            db.flush()
            state.latest_observation_id = observation.id
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


async def diagnose_pretest(db: Session, participant_id: str) -> int:
    return await diagnose_initial_test(db, participant_id)


def _current_learning_cycle_index(db: Session, participant_id: str) -> int:
    latest = (
        db.query(RetestCycle)
        .filter_by(participant_id=participant_id)
        .order_by(RetestCycle.cycle_index.desc())
        .first()
    )
    if latest and latest.status == "needs_relearning":
        return latest.cycle_index + 1
    return 1


def learning_targets(db: Session, participant_id: str) -> list[dict[str, Any]]:
    participant = get_participant(db, participant_id)
    required_cycle = _current_learning_cycle_index(db, participant.id)
    terminal_term_ids = {
        session.term_id
        for session in db.query(LearningSession)
        .filter(
            LearningSession.participant_id == participant.id,
            LearningSession.learning_cycle_index == required_cycle,
            LearningSession.status.in_(tuple(TERMINAL_LEARNING_STATUSES)),
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
            "learning_mode": "proposed_3phase" if participant.group_condition == "proposed" else "control_3phase",
        }
        for _, term, state in rows
        if term.id not in terminal_term_ids
    ]


def _term_by_slug(db: Session, term_slug: str) -> Term:
    term = db.query(Term).filter_by(slug=term_slug, is_active=True).one_or_none()
    if not term:
        raise HTTPException(status_code=404, detail="term not found")
    return term


def _initial_test_attempt_for_term(db: Session, participant_id: str, term_id: str) -> Attempt | None:
    return (
        db.query(Attempt)
        .filter_by(participant_id=participant_id, term_id=term_id, phase="initial_test")
        .order_by(Attempt.created_at.desc())
        .first()
    )


def _initial_test_context(db: Session, participant: Participant, term: Term) -> dict[str, Any]:
    attempt = _initial_test_attempt_for_term(db, participant.id, term.id)
    option = _selected_option(db, attempt) if attempt else None
    state = db.query(LearnerState).filter_by(participant_id=participant.id, term_id=term.id).one_or_none()
    assignment = db.query(TermAssignment).filter_by(participant_id=participant.id, term_id=term.id).one_or_none()
    return {
        "initial_test_diagnosis": None
        if not state
        else {
            "diagnosed_status": state.current_status,
            "misconception_type": state.primary_misconception,
            "natural_language_diagnosis": state.state_summary,
        },
        "selected_option_body": option.body if option else None,
        "selection_reason": assignment.selection_reason if assignment else None,
    }


def _pretest_context(db: Session, participant: Participant, term: Term) -> dict[str, Any]:
    return _initial_test_context(db, participant, term)


def _latest_retest_context(db: Session, participant: Participant, term: Term) -> dict[str, Any]:
    attempt = (
        db.query(Attempt)
        .filter_by(participant_id=participant.id, term_id=term.id, phase="retest")
        .order_by(Attempt.created_at.desc())
        .first()
    )
    option = _selected_option(db, attempt) if attempt else None
    cycle_result = (
        db.query(RetestCycleResult)
        .filter_by(participant_id=participant.id, term_id=term.id)
        .order_by(RetestCycleResult.created_at.desc())
        .first()
    )
    return {
        "latest_retest": None
        if not attempt
        else {
            "is_correct": attempt.is_correct,
            "diagnosed_status": attempt.diagnosed_status,
            "misconception_type": attempt.misconception_type,
            "selected_option_body": option.body if option else None,
            "becomes_learning_target": cycle_result.becomes_learning_target if cycle_result else None,
        }
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


def _public_prerequisite(row: PrerequisiteTerm, group_condition: str) -> dict[str, Any]:
    return {
        "prerequisite_id": row.id,
        "term_label": row.term_label,
        "material": row.material,
        "check_question": row.check_question,
        "generation_reason": row.generation_reason,
        "display_order": row.display_order,
        "status": row.status,
        "attempt_count": row.attempt_count,
        "max_attempts": TERM_ATTEMPT_LIMIT if group_condition == "proposed" else CONTROL_TERM_ATTEMPT_LIMIT,
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
    session = LearningSession(
        participant_id=participant.id,
        term_id=term.id,
        group_condition=participant.group_condition,
        session_index=count + 1,
        status="prerequisite",
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
    else:
        payload = {
            "participant_id": participant.id,
            "group_condition": "control",
            "target_term": {"slug": term.slug, "label": term.label, "description": term.description},
            "rag_context": _learning_rag_context(term),
        }
        result = await _ai_call(db, "generate_control_prerequisite_plan", payload)

    prerequisites = result.get("prerequisites") or []
    for index, item in enumerate(prerequisites[:3], start=1):
        db.add(
            PrerequisiteTerm(
                learning_session_id=session.id,
                term_label=item["term_label"],
                material=item["material"],
                check_question=item["check_question"],
                expected_answer=item["expected_answer"],
                generation_reason=item.get("generation_reason"),
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
    if session.group_condition == "proposed":
        current = next((row for row in prerequisites if row.status != "passed"), None)
    else:
        current = next((row for row in prerequisites if row.status in {"not_started", "review"}), None)
    return {
        "learning_session_id": session.id,
        "participant_id": participant.id,
        "group_condition": participant.group_condition,
        "status": session.status,
        "term_slug": term.slug,
        "term_label": term.label,
        "term_description": term.description,
        "prerequisites": [_public_prerequisite(row, session.group_condition) for row in prerequisites],
        "current_prerequisite_id": current.id if current else None,
        "concept": {
            "material": session.concept_material,
            "prompt": session.concept_prompt,
            "attempt_count": session.concept_phase1_attempt_count,
            "max_attempts": PHASE1_ATTEMPT_LIMIT,
            "phase1": {
                "material": session.concept_material,
                "prompt": session.concept_prompt,
                "expected_answer": session.concept_expected_answer,
                "attempt_count": session.phase1_cycle_attempt_count,
                "total_attempt_count": session.concept_phase1_attempt_count,
                "cycle_index": session.phase1_cycle_index,
                "max_attempts": PHASE1_ATTEMPT_LIMIT if session.group_condition == "proposed" else 1,
            },
            "phase2": {
                "prompt": session.phase2_prompt,
                "light_conditions": session.phase2_light_conditions,
                "expected_answer": session.phase2_expected_answer,
                "attempt_count": session.concept_phase2_attempt_count,
                "retry_count": session.phase2_retry_count,
                "max_attempts": PHASE2_ATTEMPT_LIMIT if session.group_condition == "proposed" else 1,
            },
        }
        if session.concept_material or session.phase2_prompt or session.status in {"concept_phase1", "concept_phase2"}
        else None,
        "limits": {
            "term_max_attempts": TERM_ATTEMPT_LIMIT if session.group_condition == "proposed" else CONTROL_TERM_ATTEMPT_LIMIT,
            "concept_phase1_max_attempts": PHASE1_ATTEMPT_LIMIT if session.group_condition == "proposed" else 1,
            "concept_phase2_max_attempts": PHASE2_ATTEMPT_LIMIT if session.group_condition == "proposed" else 1,
        },
        "last_feedback": session.last_feedback,
        "blocked_reason": session.blocked_reason,
        "pending_clarification": None
        if not session.pending_clarification
        else {
            "source_attempt_type": session.pending_clarification.get("source_attempt_type"),
            "source_attempt_id": session.pending_clarification.get("source_attempt_id"),
            "question": session.pending_clarification.get("question"),
        },
    }


def _session_prerequisites_payload(prereqs: list[PrerequisiteTerm]) -> list[dict[str, Any]]:
    return [
        {"id": row.id, "term_label": row.term_label, "material": row.material, "expected_answer": row.expected_answer}
        for row in prereqs
    ]


def _learning_history(db: Session, session: LearningSession) -> dict[str, Any]:
    term_attempts = (
        db.query(TermUnderstandingAttempt)
        .filter_by(learning_session_id=session.id)
        .order_by(TermUnderstandingAttempt.created_at)
        .all()
    )
    concept_attempts = (
        db.query(ConceptUnderstandingAttempt)
        .filter_by(learning_session_id=session.id)
        .order_by(ConceptUnderstandingAttempt.created_at)
        .all()
    )
    return {
        "prerequisite_attempts": [
            {
                "prerequisite_term_id": row.prerequisite_term_id,
                "attempt_index": row.attempt_index,
                "is_passed": row.is_passed,
                "score": row.score,
                "feedback": row.feedback,
                "primary_misconception_type": row.primary_misconception_type,
                "secondary_misconception_type": row.secondary_misconception_type,
            }
            for row in term_attempts[-12:]
        ],
        "concept_attempts": [
            {
                "concept_phase": row.concept_phase,
                "attempt_index": row.attempt_index,
                "is_passed": row.is_passed,
                "score": row.score,
                "feedback": row.feedback,
                "return_to_phase1": row.return_to_phase1,
                "primary_misconception_type": row.primary_misconception_type,
                "secondary_misconception_type": row.secondary_misconception_type,
            }
            for row in concept_attempts[-12:]
        ],
    }


def _learning_payload_base(db: Session, session: LearningSession, *rag_parts: object) -> dict[str, Any]:
    participant = get_participant(db, session.participant_id)
    term = db.get(Term, session.term_id)
    prereqs = _prerequisite_rows(db, session.id)
    payload: dict[str, Any] = {
        "participant_id": participant.id,
        "group_condition": participant.group_condition,
        "target_term": {"slug": term.slug, "label": term.label, "description": term.description},
        "prerequisites": _session_prerequisites_payload(prereqs),
        "rag_context": _learning_rag_context(term, *[row.term_label for row in prereqs], *rag_parts),
    }
    if participant.group_condition == "proposed":
        payload.update(_pretest_context(db, participant, term))
        payload["learning_history"] = _learning_history(db, session)
    return payload


def _effective_learning_diagnosis(result: dict[str, Any]) -> dict[str, Any]:
    confidence = float(result.get("diagnosis_confidence") or 0)
    status = result.get("diagnosed_status") or "ambiguous"
    primary = result.get("primary_misconception_type")
    if confidence < 0.75 or status == "ambiguous":
        status = "ambiguous"
        primary = None
    if status == "resolved":
        primary = None
    if status == "unknown":
        primary = "unknown"
    is_passed = bool(result.get("is_passed")) and status == "resolved"
    standard = strategy_for(primary, status, "proposed")
    recommended = result.get("recommended_strategy")
    override_reason = result.get("strategy_override_reason")
    use_override = bool(result.get("strategy_override")) and recommended in ALLOWED_ADAPTIVE_STRATEGIES and bool(override_reason)
    return {
        **result,
        "is_passed": is_passed,
        "diagnosed_status": status,
        "primary_misconception_type": primary,
        "diagnosis_confidence": confidence,
        "standard_strategy": standard,
        "applied_strategy": recommended if use_override else standard,
        "strategy_override_reason": override_reason if use_override else None,
        "requires_manual_review": bool(result.get("requires_manual_review")) or confidence < 0.5,
    }


def _latest_observation(
    db: Session,
    participant_id: str,
    term_id: str,
    prerequisite_term_id: str | None,
) -> MisconceptionObservation | None:
    query = db.query(MisconceptionObservation).filter_by(participant_id=participant_id, term_id=term_id)
    if prerequisite_term_id:
        query = query.filter_by(prerequisite_term_id=prerequisite_term_id)
    else:
        query = query.filter(MisconceptionObservation.prerequisite_term_id.is_(None))
    return query.order_by(MisconceptionObservation.created_at.desc()).first()


def _record_learning_observation(
    db: Session,
    *,
    session: LearningSession,
    source_phase: str,
    source_attempt_type: str,
    source_attempt_id: str,
    diagnosis: dict[str, Any],
    prerequisite: PrerequisiteTerm | None = None,
) -> MisconceptionObservation:
    previous = _latest_observation(db, session.participant_id, session.term_id, prerequisite.id if prerequisite else None)
    previous_status = (
        previous.diagnosed_status
        if previous
        else (prerequisite.current_status if prerequisite else db.query(LearnerState).filter_by(participant_id=session.participant_id, term_id=session.term_id).one().current_status)
    )
    previous_type = (
        previous.primary_misconception_type
        if previous
        else (prerequisite.primary_misconception_type if prerequisite else db.query(LearnerState).filter_by(participant_id=session.participant_id, term_id=session.term_id).one().primary_misconception)
    )
    status = diagnosis["diagnosed_status"]
    current_type = diagnosis.get("primary_misconception_type")
    persistence = bool(current_type and current_type == previous_type and status == "misconception")
    prior_resolved = (
        db.query(MisconceptionObservation)
        .filter_by(
            participant_id=session.participant_id,
            term_id=session.term_id,
            prerequisite_term_id=prerequisite.id if prerequisite else None,
            diagnosed_status="resolved",
        )
        .first()
    )
    prior_same = (
        db.query(MisconceptionObservation)
        .filter_by(
            participant_id=session.participant_id,
            term_id=session.term_id,
            prerequisite_term_id=prerequisite.id if prerequisite else None,
            primary_misconception_type=current_type,
        )
        .first()
        if current_type
        else None
    )
    recurrence = bool(current_type and prior_resolved and prior_same)
    if status == "resolved":
        resolution_stage = "confirmed_in_learning" if source_phase == "concept_phase2" else "provisional"
        transition_type = "resolution"
    elif persistence:
        resolution_stage = "none"
        transition_type = "persistence"
    elif recurrence:
        resolution_stage = "none"
        transition_type = "recurrence"
    elif previous_type and current_type and previous_type != current_type:
        resolution_stage = "none"
        transition_type = f"{previous_type}_to_{current_type}"
    else:
        resolution_stage = "none"
        transition_type = "initial" if not previous else "status_change"
    observation = MisconceptionObservation(
        participant_id=session.participant_id,
        term_id=session.term_id,
        learning_session_id=session.id,
        prerequisite_term_id=prerequisite.id if prerequisite else None,
        source_phase=source_phase,
        source_attempt_type=source_attempt_type,
        source_attempt_id=source_attempt_id,
        diagnosed_status=status,
        primary_misconception_type=current_type,
        secondary_misconception_type=diagnosis.get("secondary_misconception_type"),
        diagnosis_confidence=diagnosis.get("diagnosis_confidence"),
        diagnosis_evidence=diagnosis.get("diagnosis_evidence"),
        previous_status=previous_status,
        previous_misconception_type=previous_type,
        resolution_stage=resolution_stage,
        transition_type=transition_type,
        is_persistence=persistence,
        is_recurrence=recurrence,
        standard_strategy=diagnosis.get("standard_strategy"),
        applied_strategy=diagnosis.get("applied_strategy"),
        strategy_override_reason=diagnosis.get("strategy_override_reason"),
        requires_manual_review=bool(diagnosis.get("requires_manual_review")),
    )
    db.add(observation)
    db.flush()
    return observation


def _apply_observation_state(
    db: Session,
    session: LearningSession,
    observation: MisconceptionObservation,
    prerequisite: PrerequisiteTerm | None = None,
) -> None:
    if observation.diagnosed_status == "ambiguous":
        return
    if prerequisite:
        prerequisite.current_status = observation.diagnosed_status
        prerequisite.primary_misconception_type = observation.primary_misconception_type
        prerequisite.secondary_misconception_type = observation.secondary_misconception_type
        prerequisite.resolution_stage = observation.resolution_stage
        prerequisite.teaching_strategy = observation.applied_strategy
        prerequisite.latest_observation_id = observation.id
        return
    state = db.query(LearnerState).filter_by(participant_id=session.participant_id, term_id=session.term_id).one()
    state.current_status = observation.diagnosed_status
    state.primary_misconception = observation.primary_misconception_type
    state.secondary_misconception = observation.secondary_misconception_type
    state.previous_teaching_strategy = state.teaching_strategy
    state.teaching_strategy = observation.applied_strategy
    state.resolution_stage = observation.resolution_stage
    state.latest_observation_id = observation.id
    state.updated_reason = observation.transition_type


async def _generate_and_store_support(
    db: Session,
    session: LearningSession,
    observation: MisconceptionObservation,
    *,
    mode: str,
) -> AdaptiveSupportEvent:
    term = db.get(Term, session.term_id)
    payload = _learning_payload_base(db, session, observation.diagnosis_evidence)
    payload.update(
        {
            "mode": mode,
            "observation": {
                "diagnosed_status": observation.diagnosed_status,
                "primary_misconception_type": observation.primary_misconception_type,
                "secondary_misconception_type": observation.secondary_misconception_type,
                "diagnosis_evidence": observation.diagnosis_evidence,
                "resolution_stage": observation.resolution_stage,
                "standard_strategy": observation.standard_strategy,
                "applied_strategy": observation.applied_strategy,
            },
            "rag_context": _learning_rag_context(term, observation.diagnosis_evidence, observation.applied_strategy),
        }
    )
    result = await _ai_call(db, "generate_adaptive_support", payload)
    event = AdaptiveSupportEvent(
        misconception_observation_id=observation.id,
        learning_session_id=session.id,
        mode=mode,
        feedback=result["feedback"],
        supplemental_material=result.get("supplemental_material"),
        next_check_question=result.get("next_check_question"),
        diagnostic_focus=result.get("diagnostic_focus"),
        rag_sources=result.get("rag_sources"),
        general_knowledge_supplement=result.get("general_knowledge_supplement"),
        ai_call_log_id=result.get("_ai_call_log_id"),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def _prerequisites_complete(session: LearningSession, prerequisites: list[PrerequisiteTerm]) -> bool:
    if session.group_condition == "proposed":
        return bool(prerequisites) and all(row.status == "passed" for row in prerequisites)
    return bool(prerequisites) and all(row.status in {"passed", "failed"} for row in prerequisites)


async def _ensure_concept_phase1_material(db: Session, session: LearningSession) -> None:
    if session.concept_material:
        session.status = "concept_phase1"
        db.commit()
        return
    payload = _learning_payload_base(db, session)
    result = await _ai_call(db, "generate_concept_phase1_material", payload)
    session.concept_material = result["concept_material"]
    session.concept_prompt = result["concept_prompt"]
    session.concept_expected_answer = result["expected_answer"]
    session.status = "concept_phase1"
    db.commit()


async def _ensure_concept_phase2_prompt(db: Session, session: LearningSession) -> None:
    if session.phase2_prompt:
        session.status = "concept_phase2"
        db.commit()
        return
    payload = _learning_payload_base(db, session, session.concept_prompt, session.last_feedback)
    payload.update(
        {
            "material": session.concept_material,
            "prompt": session.concept_prompt,
            "expected_answer": session.concept_expected_answer,
        }
    )
    result = await _ai_call(db, "generate_concept_phase2_prompt", payload)
    session.phase2_prompt = result["phase2_prompt"]
    session.phase2_light_conditions = result["light_conditions"]
    session.phase2_expected_answer = result["expected_answer"]
    session.status = "concept_phase2"
    db.commit()


async def _ensure_concept_material(db: Session, session: LearningSession) -> None:
    await _ensure_concept_phase1_material(db, session)


async def submit_prerequisite_attempt(
    db: Session,
    session_id: str,
    prerequisite_id: str,
    learner_answer: str,
    attempt_kind: str = "normal",
    clarification_parent_attempt_id: str | None = None,
) -> dict[str, Any]:
    session = db.get(LearningSession, session_id)
    prereq = db.get(PrerequisiteTerm, prerequisite_id)
    if not session or not prereq or prereq.learning_session_id != session_id:
        raise HTTPException(status_code=404, detail="prerequisite not found")
    if session.status in TERMINAL_LEARNING_STATUSES:
        raise HTTPException(status_code=400, detail=f"session is {session.status}")

    participant = get_participant(db, session.participant_id)
    term = db.get(Term, session.term_id)
    is_clarification = attempt_kind == "clarification"
    if is_clarification:
        pending = session.pending_clarification or {}
        if pending.get("source_attempt_type") != "prerequisite" or pending.get("prerequisite_id") != prereq.id:
            raise HTTPException(status_code=400, detail="clarification is not pending")
        clarification_parent_attempt_id = clarification_parent_attempt_id or pending.get("source_attempt_id")
    attempt_index = (
        db.query(func.count(TermUnderstandingAttempt.id)).filter_by(prerequisite_term_id=prereq.id).scalar() or 0
    ) + 1
    max_attempts = TERM_ATTEMPT_LIMIT if session.group_condition == "proposed" else CONTROL_TERM_ATTEMPT_LIMIT
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
        "max_attempts": max_attempts,
        "attempt_kind": attempt_kind,
        "rag_context": _learning_rag_context(term, prereq.term_label, learner_answer),
    }
    if is_clarification:
        payload["prerequisite"]["check_question"] = (session.pending_clarification or {}).get("question") or prereq.check_question
    if session.group_condition == "proposed":
        payload.update(_pretest_context(db, participant, term))
        payload["learning_history"] = _learning_history(db, session)
    attempt = TermUnderstandingAttempt(
        prerequisite_term_id=prereq.id,
        participant_id=participant.id,
        learning_session_id=session.id,
        attempt_index=attempt_index,
        learner_answer=learner_answer,
        is_passed=False,
        feedback="診断中",
        attempt_kind=attempt_kind,
        counts_toward_limit=not is_clarification,
        clarification_parent_attempt_id=clarification_parent_attempt_id,
        presented_question=(session.pending_clarification or {}).get("question") if is_clarification else prereq.check_question,
        diagnostic_focus=(session.pending_clarification or {}).get("diagnostic_focus") if is_clarification else prereq.diagnostic_focus,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    result = await _ai_call(db, "grade_prerequisite_answer", payload)
    support: AdaptiveSupportEvent | None = None
    if session.group_condition == "proposed":
        diagnosis = _effective_learning_diagnosis(result)
        observation = _record_learning_observation(
            db,
            session=session,
            source_phase="prerequisite",
            source_attempt_type=attempt_kind,
            source_attempt_id=attempt.id,
            diagnosis=diagnosis,
            prerequisite=prereq,
        )
        attempt.diagnosis_observation_id = observation.id
        attempt.primary_misconception_type = observation.primary_misconception_type
        attempt.secondary_misconception_type = observation.secondary_misconception_type
        attempt.is_passed = bool(diagnosis["is_passed"])
        attempt.score = result.get("score")
        attempt.grading_json = result
        attempt.feedback = result.get("feedback") or ""
        if not is_clarification:
            prereq.attempt_count += 1
        _apply_observation_state(db, session, observation, prereq)
        db.commit()
        mode = "clarification" if observation.diagnosed_status == "ambiguous" else "remediation"
        support = await _generate_and_store_support(db, session, observation, mode=mode)
        attempt.feedback = support.feedback
        attempt.remediation_material = support.supplemental_material
        attempt.diagnostic_focus = support.diagnostic_focus
        if observation.diagnosed_status == "ambiguous" and not is_clarification:
            session.pending_clarification = {
                "source_attempt_type": "prerequisite",
                "source_attempt_id": attempt.id,
                "observation_id": observation.id,
                "prerequisite_id": prereq.id,
                "question": support.next_check_question,
                "diagnostic_focus": support.diagnostic_focus,
            }
            prereq.status = "review"
            session.last_feedback = support.feedback
            db.commit()
            return {
                "is_passed": False,
                "feedback": support.feedback,
                "supplemental_material": support.supplemental_material,
                "next_check_question": support.next_check_question,
                "requires_clarification": True,
                "clarification_parent_attempt_id": attempt.id,
                "session": learning_session_state(db, session.id),
            }
        session.pending_clarification = None
        is_passed = attempt.is_passed
    else:
        is_passed = bool(result["is_passed"])
        attempt.is_passed = is_passed
        attempt.score = result.get("score")
        attempt.feedback = result["feedback"]
        attempt.remediation_material = result.get("remediation_material")
        attempt.grading_json = result
        if not is_clarification:
            prereq.attempt_count += 1

    prereq.last_feedback = support.feedback if support else result["feedback"]
    prereq.remediation_material = support.supplemental_material if support else result.get("remediation_material")
    if support and support.next_check_question and not is_passed:
        prereq.check_question = support.next_check_question
        prereq.diagnostic_focus = support.diagnostic_focus
    prereq.status = "passed" if is_passed else ("failed" if prereq.attempt_count >= max_attempts else "review")
    session.last_feedback = prereq.last_feedback

    prerequisites = _prerequisite_rows(db, session.id)
    if session.group_condition == "proposed" and not is_passed and prereq.attempt_count >= TERM_ATTEMPT_LIMIT:
        session.status = "blocked"
        session.blocked_reason = f"{prereq.term_label} の理解確認を2回通過できませんでした。"
        session.completed_at = now()
    elif _prerequisites_complete(session, prerequisites):
        session.term_pass_count = sum(1 for row in prerequisites if row.status == "passed")
        await _ensure_concept_phase1_material(db, session)
    else:
        session.status = "prerequisite"
    db.commit()
    return {
        "is_passed": is_passed,
        "feedback": prereq.last_feedback,
        "supplemental_material": prereq.remediation_material,
        "next_check_question": support.next_check_question if support and not is_passed else None,
        "requires_clarification": False,
        "session": learning_session_state(db, session.id),
    }


def _ids_for_labels(prereqs: list[PrerequisiteTerm], labels: list[str]) -> list[str]:
    out: list[str] = []
    for label in labels:
        for row in prereqs:
            if row.term_label == label and row.id not in out:
                out.append(row.id)
                break
    return out


async def submit_concept_phase1_attempt(
    db: Session,
    session_id: str,
    learner_answer: str,
    attempt_kind: str = "normal",
    clarification_parent_attempt_id: str | None = None,
) -> dict[str, Any]:
    session = db.get(LearningSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="learning session not found")
    if session.status in TERMINAL_LEARNING_STATUSES:
        raise HTTPException(status_code=400, detail=f"session is {session.status}")
    prereqs = _prerequisite_rows(db, session.id)
    if not _prerequisites_complete(session, prereqs):
        raise HTTPException(status_code=400, detail="prerequisites must be completed first")
    await _ensure_concept_phase1_material(db, session)

    participant = get_participant(db, session.participant_id)
    term = db.get(Term, session.term_id)
    is_clarification = attempt_kind == "clarification"
    if is_clarification:
        pending = session.pending_clarification or {}
        if pending.get("source_attempt_type") != "concept_phase1":
            raise HTTPException(status_code=400, detail="clarification is not pending")
        clarification_parent_attempt_id = clarification_parent_attempt_id or pending.get("source_attempt_id")
    attempt_index = (
        db.query(func.count(ConceptUnderstandingAttempt.id))
        .filter_by(learning_session_id=session.id, concept_phase="phase1")
        .scalar()
        or 0
    ) + 1
    max_attempts = PHASE1_ATTEMPT_LIMIT if session.group_condition == "proposed" else 1
    payload = _learning_payload_base(db, session, session.concept_prompt, learner_answer)
    payload.update(
        {
            "concept_material": session.concept_material,
            "concept_prompt": session.concept_prompt,
            "expected_answer": session.concept_expected_answer,
            "learner_answer": learner_answer,
            "attempt_index": attempt_index,
            "max_attempts": max_attempts,
            "attempt_kind": attempt_kind,
        }
    )
    if is_clarification:
        payload["concept_prompt"] = (session.pending_clarification or {}).get("question") or session.concept_prompt
    attempt = ConceptUnderstandingAttempt(
        learning_session_id=session.id,
        participant_id=participant.id,
        attempt_index=attempt_index,
        concept_phase="phase1",
        concept_material=session.concept_material or "",
        prompt=(session.pending_clarification or {}).get("question") if is_clarification else (session.concept_prompt or ""),
        material_shown=True,
        learner_answer=learner_answer,
        is_passed=False,
        feedback="診断中",
        missing_prerequisite_ids=[],
        review_prerequisite_ids=[],
        independent_explanation_success=None,
        return_to_phase1=False,
        phase1_cycle_index=session.phase1_cycle_index,
        attempt_kind=attempt_kind,
        counts_toward_limit=not is_clarification,
        clarification_parent_attempt_id=clarification_parent_attempt_id,
        presented_question=(session.pending_clarification or {}).get("question") if is_clarification else session.concept_prompt,
        diagnostic_focus=(session.pending_clarification or {}).get("diagnostic_focus") if is_clarification else None,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    result = await _ai_call(db, "grade_concept_phase1_answer", payload)
    missing_ids = _ids_for_labels(prereqs, result.get("missing_prerequisite_labels") or [])
    review_ids = _ids_for_labels(prereqs, result.get("review_prerequisite_labels") or [])
    support: AdaptiveSupportEvent | None = None
    if session.group_condition == "proposed":
        diagnosis = _effective_learning_diagnosis(result)
        observation = _record_learning_observation(
            db,
            session=session,
            source_phase="concept_phase1",
            source_attempt_type=attempt_kind,
            source_attempt_id=attempt.id,
            diagnosis=diagnosis,
        )
        attempt.diagnosis_observation_id = observation.id
        attempt.primary_misconception_type = observation.primary_misconception_type
        attempt.secondary_misconception_type = observation.secondary_misconception_type
        attempt.is_passed = bool(diagnosis["is_passed"])
        attempt.score = result.get("score")
        attempt.feedback = result.get("feedback") or ""
        attempt.missing_prerequisite_ids = missing_ids
        attempt.review_prerequisite_ids = review_ids
        attempt.rubric_scores = result.get("rubric_scores")
        attempt.grading_json = result
        if not is_clarification:
            session.concept_phase1_attempt_count += 1
            session.phase1_cycle_attempt_count += 1
            session.concept_attempt_count = session.concept_phase1_attempt_count
        _apply_observation_state(db, session, observation)
        db.commit()
        mode = "clarification" if observation.diagnosed_status == "ambiguous" else "remediation"
        support = await _generate_and_store_support(db, session, observation, mode=mode)
        if observation.diagnosed_status == "ambiguous" and not is_clarification:
            session.pending_clarification = {
                "source_attempt_type": "concept_phase1",
                "source_attempt_id": attempt.id,
                "observation_id": observation.id,
                "question": support.next_check_question,
                "diagnostic_focus": support.diagnostic_focus,
            }
            attempt.feedback = support.feedback
            attempt.diagnostic_focus = support.diagnostic_focus
            db.commit()
            return {
                "is_passed": False,
                "feedback": support.feedback,
                "supplemental_material": support.supplemental_material,
                "next_check_question": support.next_check_question,
                "requires_clarification": True,
                "clarification_parent_attempt_id": attempt.id,
                "missing_prerequisite_ids": [],
                "review_prerequisite_ids": [],
                "session": learning_session_state(db, session.id),
            }
        session.pending_clarification = None
        is_passed = attempt.is_passed
    else:
        is_passed = bool(result["is_passed"])
        attempt.is_passed = is_passed

    attempt.score = result.get("score")
    attempt.feedback = support.feedback if support else result["feedback"]
    attempt.missing_prerequisite_ids = missing_ids
    attempt.review_prerequisite_ids = review_ids
    attempt.rubric_scores = result.get("rubric_scores")
    attempt.grading_json = result
    if support:
        attempt.diagnostic_focus = support.diagnostic_focus
    if session.group_condition == "control" and not is_clarification:
        session.concept_phase1_attempt_count += 1
        session.phase1_cycle_attempt_count += 1
        session.concept_attempt_count = session.concept_phase1_attempt_count
    session.last_feedback = attempt.feedback

    if session.group_condition == "proposed":
        for label in result.get("confirmed_prerequisite_labels") or []:
            row = next((item for item in prereqs if item.term_label == label), None)
            if row:
                row.current_status = "resolved"
                row.resolution_stage = "confirmed_in_learning"
        for prereq_id in missing_ids + review_ids:
            row = db.get(PrerequisiteTerm, prereq_id)
            if row:
                row.status = "review"
                row.attempt_count = 0
    if session.group_condition == "control":
        await _ensure_concept_phase2_prompt(db, session)
    elif is_passed:
        await _ensure_concept_phase2_prompt(db, session)
    elif session.phase1_cycle_attempt_count >= PHASE1_ATTEMPT_LIMIT:
        session.status = "failed_phase1"
        session.blocked_reason = "概念フェーズ1を3回通過できませんでした。"
        session.completed_at = now()
    else:
        session.status = "prerequisite" if (missing_ids or review_ids) else "concept_phase1"
        if support and not (missing_ids or review_ids):
            session.concept_material = support.supplemental_material or session.concept_material
            session.concept_prompt = support.next_check_question or session.concept_prompt
    db.commit()
    return {
        "is_passed": is_passed,
        "feedback": attempt.feedback,
        "supplemental_material": support.supplemental_material if support else None,
        "next_check_question": support.next_check_question if support and not is_passed else None,
        "requires_clarification": False,
        "missing_prerequisite_ids": missing_ids,
        "review_prerequisite_ids": review_ids,
        "session": learning_session_state(db, session.id),
    }


async def submit_concept_phase2_attempt(
    db: Session,
    session_id: str,
    learner_answer: str,
    attempt_kind: str = "normal",
    clarification_parent_attempt_id: str | None = None,
) -> dict[str, Any]:
    session = db.get(LearningSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="learning session not found")
    if session.status in TERMINAL_LEARNING_STATUSES:
        raise HTTPException(status_code=400, detail=f"session is {session.status}")
    if not session.concept_material:
        raise HTTPException(status_code=400, detail="phase1 material must exist first")
    await _ensure_concept_phase2_prompt(db, session)

    is_clarification = attempt_kind == "clarification"
    if is_clarification:
        pending = session.pending_clarification or {}
        if pending.get("source_attempt_type") != "concept_phase2":
            raise HTTPException(status_code=400, detail="clarification is not pending")
        clarification_parent_attempt_id = clarification_parent_attempt_id or pending.get("source_attempt_id")
    attempt_index = (
        db.query(func.count(ConceptUnderstandingAttempt.id))
        .filter_by(learning_session_id=session.id, concept_phase="phase2")
        .scalar()
        or 0
    ) + 1
    max_attempts = PHASE2_ATTEMPT_LIMIT if session.group_condition == "proposed" else 1
    payload = _learning_payload_base(db, session, session.phase2_prompt, session.phase2_light_conditions, learner_answer)
    payload.update(
        {
            "phase2_prompt": session.phase2_prompt,
            "light_conditions": session.phase2_light_conditions,
            "expected_answer": session.phase2_expected_answer,
            "learner_answer": learner_answer,
            "attempt_index": attempt_index,
            "max_attempts": max_attempts,
            "attempt_kind": attempt_kind,
        }
    )
    if is_clarification:
        payload["phase2_prompt"] = (session.pending_clarification or {}).get("question") or session.phase2_prompt
    attempt = ConceptUnderstandingAttempt(
        learning_session_id=session.id,
        participant_id=session.participant_id,
        attempt_index=attempt_index,
        concept_phase="phase2",
        concept_material=session.concept_material or "",
        prompt=(session.pending_clarification or {}).get("question") if is_clarification else (session.phase2_prompt or ""),
        material_shown=False,
        light_condition_text=session.phase2_light_conditions,
        learner_answer=learner_answer,
        is_passed=False,
        feedback="診断中",
        missing_prerequisite_ids=[],
        review_prerequisite_ids=[],
        return_to_phase1=False,
        phase1_cycle_index=session.phase1_cycle_index,
        attempt_kind=attempt_kind,
        counts_toward_limit=not is_clarification,
        clarification_parent_attempt_id=clarification_parent_attempt_id,
        presented_question=(session.pending_clarification or {}).get("question") if is_clarification else session.phase2_prompt,
        diagnostic_focus=(session.pending_clarification or {}).get("diagnostic_focus") if is_clarification else None,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    result = await _ai_call(db, "grade_concept_phase2_answer", payload)
    support: AdaptiveSupportEvent | None = None
    if session.group_condition == "proposed":
        diagnosis = _effective_learning_diagnosis(result)
        observation = _record_learning_observation(
            db,
            session=session,
            source_phase="concept_phase2",
            source_attempt_type=attempt_kind,
            source_attempt_id=attempt.id,
            diagnosis=diagnosis,
        )
        attempt.diagnosis_observation_id = observation.id
        attempt.primary_misconception_type = observation.primary_misconception_type
        attempt.secondary_misconception_type = observation.secondary_misconception_type
        attempt.is_passed = bool(diagnosis["is_passed"])
        attempt.score = result.get("score")
        attempt.feedback = result.get("feedback") or ""
        attempt.independent_explanation_success = result.get("independent_explanation_success")
        attempt.return_to_phase1 = not attempt.is_passed
        attempt.rubric_scores = result.get("rubric_scores")
        attempt.grading_json = result
        if not is_clarification:
            session.concept_phase2_attempt_count += 1
        _apply_observation_state(db, session, observation)
        db.commit()
        mode = "clarification" if observation.diagnosed_status == "ambiguous" else "remediation"
        support = await _generate_and_store_support(db, session, observation, mode=mode)
        if observation.diagnosed_status == "ambiguous" and not is_clarification:
            session.pending_clarification = {
                "source_attempt_type": "concept_phase2",
                "source_attempt_id": attempt.id,
                "observation_id": observation.id,
                "question": support.next_check_question,
                "diagnostic_focus": support.diagnostic_focus,
            }
            attempt.feedback = support.feedback
            attempt.diagnostic_focus = support.diagnostic_focus
            db.commit()
            return {
                "is_passed": False,
                "feedback": support.feedback,
                "supplemental_material": support.supplemental_material,
                "next_check_question": support.next_check_question,
                "requires_clarification": True,
                "clarification_parent_attempt_id": attempt.id,
                "return_to_phase1": False,
                "session": learning_session_state(db, session.id),
            }
        session.pending_clarification = None
        is_passed = attempt.is_passed
    else:
        is_passed = bool(result["is_passed"])
        attempt.is_passed = is_passed

    attempt.score = result.get("score")
    attempt.feedback = support.feedback if support else result["feedback"]
    attempt.independent_explanation_success = result.get("independent_explanation_success")
    attempt.return_to_phase1 = not is_passed and session.group_condition == "proposed"
    attempt.rubric_scores = result.get("rubric_scores")
    attempt.grading_json = result
    if support:
        attempt.diagnostic_focus = support.diagnostic_focus
    if session.group_condition == "control" and not is_clarification:
        session.concept_phase2_attempt_count += 1
    session.last_feedback = attempt.feedback
    if session.group_condition == "control":
        session.status = "completed"
        session.completed_at = now()
    elif is_passed:
        session.status = "completed"
        session.completed_at = now()
    elif session.concept_phase2_attempt_count >= PHASE2_ATTEMPT_LIMIT:
        session.status = "failed_phase2"
        session.blocked_reason = "概念フェーズ2を3回通過できませんでした。"
        session.completed_at = now()
    else:
        session.phase2_retry_count += 1
        session.phase1_cycle_index += 1
        session.phase1_cycle_attempt_count = 0
        session.concept_material = support.supplemental_material if support and support.supplemental_material else session.concept_material
        session.concept_prompt = support.next_check_question if support and support.next_check_question else session.concept_prompt
        session.phase2_prompt = None
        session.phase2_light_conditions = None
        session.phase2_expected_answer = None
        session.status = "concept_phase1"
    db.commit()
    return {
        "is_passed": is_passed,
        "feedback": attempt.feedback,
        "supplemental_material": support.supplemental_material if support else None,
        "next_check_question": support.next_check_question if support and not is_passed else None,
        "requires_clarification": False,
        "return_to_phase1": session.group_condition == "proposed" and not is_passed,
        "session": learning_session_state(db, session.id),
    }


async def submit_concept_attempt(db: Session, session_id: str, learner_answer: str) -> dict[str, Any]:
    return await submit_concept_phase1_attempt(db, session_id, learner_answer)


async def retry_adaptive_support(
    db: Session,
    session_id: str,
    observation_id: str,
) -> dict[str, Any]:
    session = db.get(LearningSession, session_id)
    observation = db.get(MisconceptionObservation, observation_id)
    if not session or not observation or observation.learning_session_id != session.id:
        raise HTTPException(status_code=404, detail="diagnosis observation not found")
    if session.group_condition != "proposed":
        raise HTTPException(status_code=400, detail="adaptive support is proposed-only")
    existing = (
        db.query(AdaptiveSupportEvent)
        .filter_by(misconception_observation_id=observation.id)
        .order_by(AdaptiveSupportEvent.created_at.desc())
        .first()
    )
    if existing:
        return {
            "feedback": existing.feedback,
            "supplemental_material": existing.supplemental_material,
            "next_check_question": existing.next_check_question,
            "requires_clarification": existing.mode == "clarification",
            "session": learning_session_state(db, session.id),
        }
    mode = "clarification" if observation.diagnosed_status == "ambiguous" else "remediation"
    support = await _generate_and_store_support(db, session, observation, mode=mode)
    session.last_feedback = support.feedback
    if mode == "clarification":
        session.pending_clarification = {
            "source_attempt_type": observation.source_phase,
            "source_attempt_id": observation.source_attempt_id,
            "observation_id": observation.id,
            "prerequisite_id": observation.prerequisite_term_id,
            "question": support.next_check_question,
            "diagnostic_focus": support.diagnostic_focus,
        }
    elif observation.source_phase == "prerequisite" and observation.prerequisite_term_id:
        prereq = db.get(PrerequisiteTerm, observation.prerequisite_term_id)
        attempt = db.get(TermUnderstandingAttempt, observation.source_attempt_id)
        if prereq and attempt:
            attempt.feedback = support.feedback
            attempt.remediation_material = support.supplemental_material
            attempt.diagnostic_focus = support.diagnostic_focus
            prereq.last_feedback = support.feedback
            prereq.remediation_material = support.supplemental_material
            if support.next_check_question and not attempt.is_passed:
                prereq.check_question = support.next_check_question
            prereq.status = "passed" if attempt.is_passed else ("failed" if prereq.attempt_count >= TERM_ATTEMPT_LIMIT else "review")
            prerequisites = _prerequisite_rows(db, session.id)
            if not attempt.is_passed and prereq.attempt_count >= TERM_ATTEMPT_LIMIT:
                session.status = "blocked"
                session.completed_at = now()
            elif _prerequisites_complete(session, prerequisites):
                await _ensure_concept_phase1_material(db, session)
            else:
                session.status = "prerequisite"
    elif observation.source_phase == "concept_phase1":
        attempt = db.get(ConceptUnderstandingAttempt, observation.source_attempt_id)
        if attempt:
            attempt.feedback = support.feedback
            attempt.diagnostic_focus = support.diagnostic_focus
            if attempt.is_passed:
                await _ensure_concept_phase2_prompt(db, session)
            elif session.phase1_cycle_attempt_count >= PHASE1_ATTEMPT_LIMIT:
                session.status = "failed_phase1"
                session.completed_at = now()
            elif attempt.missing_prerequisite_ids or attempt.review_prerequisite_ids:
                session.status = "prerequisite"
            else:
                session.concept_material = support.supplemental_material or session.concept_material
                session.concept_prompt = support.next_check_question or session.concept_prompt
                session.status = "concept_phase1"
    elif observation.source_phase == "concept_phase2":
        attempt = db.get(ConceptUnderstandingAttempt, observation.source_attempt_id)
        if attempt:
            attempt.feedback = support.feedback
            attempt.diagnostic_focus = support.diagnostic_focus
            if attempt.is_passed:
                session.status = "completed"
                session.completed_at = now()
            elif session.concept_phase2_attempt_count >= PHASE2_ATTEMPT_LIMIT:
                session.status = "failed_phase2"
                session.completed_at = now()
            else:
                session.phase2_retry_count += 1
                session.phase1_cycle_index += 1
                session.phase1_cycle_attempt_count = 0
                session.concept_material = support.supplemental_material or session.concept_material
                session.concept_prompt = support.next_check_question or session.concept_prompt
                session.phase2_prompt = None
                session.phase2_light_conditions = None
                session.phase2_expected_answer = None
                session.status = "concept_phase1"
    db.commit()
    return {
        "feedback": support.feedback,
        "supplemental_material": support.supplemental_material,
        "next_check_question": support.next_check_question,
        "requires_clarification": mode == "clarification",
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


def _latest_attempts_by_term(db: Session, participant_id: str, phase: str) -> list[Attempt]:
    attempts = (
        db.query(Attempt)
        .filter_by(participant_id=participant_id, phase=phase)
        .order_by(Attempt.created_at.desc())
        .all()
    )
    latest: dict[str, Attempt] = {}
    for attempt in attempts:
        latest.setdefault(attempt.term_id, attempt)
    return list(latest.values())


def _score_test_attempts(db: Session, participant: Participant, attempts: list[Attempt], phase: str) -> None:
    for attempt in attempts:
        option = _selected_option(db, attempt)
        if not option:
            raise HTTPException(status_code=400, detail=f"{phase} requires a selected option")
        attempt.is_correct = option.is_correct
        attempt.score = 1.0 if option.is_correct else 0.0
        attempt.diagnosed_status = "resolved" if option.is_correct else ("unknown" if option.misconception_type == "unknown" else "misconception")
        attempt.misconception_type = None if option.is_correct else option.misconception_type
        attempt.secondary_misconception_type = None
        state = db.query(LearnerState).filter_by(participant_id=participant.id, term_id=attempt.term_id).one_or_none()
        if not state:
            continue
        previous = (
            db.query(Attempt)
            .filter_by(participant_id=participant.id, term_id=attempt.term_id, phase="initial_test")
            .order_by(Attempt.created_at.desc())
            .first()
        )
        if previous and previous.misconception_type in {"M1", "M2", "M3"} and previous.misconception_type == attempt.misconception_type:
            attempt.recurrence_flag = True
            state.recurrence_count += 1
            db.add(
                RecurrenceEvent(
                    participant_id=participant.id,
                    term_id=attempt.term_id,
                    previous_attempt_id=previous.id,
                    current_attempt_id=attempt.id,
                    previous_misconception_type=previous.misconception_type,
                    current_misconception_type=attempt.misconception_type,
                    is_same_type=True,
                    phase=phase,
                )
            )
        previous_observation = _latest_observation(db, participant.id, attempt.term_id, None)
        status = "resolved" if attempt.is_correct else ("unknown" if attempt.misconception_type == "unknown" else "misconception")
        observation = MisconceptionObservation(
            participant_id=participant.id,
            term_id=attempt.term_id,
            source_phase=phase,
            source_attempt_type="test",
            source_attempt_id=attempt.id,
            diagnosed_status=status,
            primary_misconception_type=None if attempt.is_correct else attempt.misconception_type,
            secondary_misconception_type=None,
            diagnosis_confidence=1.0,
            diagnosis_evidence=option.body,
            previous_status=previous_observation.diagnosed_status if previous_observation else state.current_status,
            previous_misconception_type=previous_observation.primary_misconception_type if previous_observation else state.primary_misconception,
            resolution_stage="confirmed_by_retest" if phase == "retest" and attempt.is_correct else ("confirmed_by_final_test" if phase == "final_test" and attempt.is_correct else "none"),
            transition_type="resolution" if attempt.is_correct else ("recurrence" if attempt.recurrence_flag else f"{phase}_change"),
            is_recurrence=attempt.recurrence_flag,
            standard_strategy=strategy_for(attempt.misconception_type, status, participant.group_condition),
            applied_strategy=strategy_for(attempt.misconception_type, status, participant.group_condition),
        )
        db.add(observation)
        db.flush()
        state.current_status = "resolved" if attempt.is_correct else status
        state.primary_misconception = None if attempt.is_correct else attempt.misconception_type
        state.last_attempt_id = attempt.id
        state.latest_observation_id = observation.id
        state.resolution_stage = observation.resolution_stage


async def score_retest(db: Session, participant_id: str) -> dict[str, Any]:
    participant = get_participant(db, participant_id)
    attempts = _latest_attempts_by_term(db, participant.id, "retest")
    if len(attempts) < 5:
        raise HTTPException(status_code=400, detail="retest requires all five concept attempts")
    _score_test_attempts(db, participant, attempts, "retest")
    cycle_index = (db.query(func.max(RetestCycle.cycle_index)).filter_by(participant_id=participant.id).scalar() or 0) + 1
    all_correct = all(bool(attempt.is_correct) for attempt in attempts)
    cycle = RetestCycle(
        participant_id=participant.id,
        cycle_index=cycle_index,
        status="passed" if all_correct else "needs_relearning",
        all_correct=all_correct,
        relearning_target_count=sum(1 for attempt in attempts if not attempt.is_correct),
        completed_at=now(),
    )
    db.add(cycle)
    db.flush()
    for attempt in attempts:
        becomes_target = not bool(attempt.is_correct)
        db.add(
            RetestCycleResult(
                retest_cycle_id=cycle.id,
                participant_id=participant.id,
                term_id=attempt.term_id,
                attempt_id=attempt.id,
                is_correct=bool(attempt.is_correct),
                misconception_type=attempt.misconception_type,
                becomes_learning_target=becomes_target,
            )
        )
        assignment = db.query(TermAssignment).filter_by(participant_id=participant.id, term_id=attempt.term_id).one_or_none()
        score, reason = _priority(attempt)
        if not assignment:
            assignment = TermAssignment(
                participant_id=participant.id,
                term_id=attempt.term_id,
                group_condition=participant.group_condition,
            )
            db.add(assignment)
        assignment.is_learning_target = becomes_target
        assignment.priority_score = score if becomes_target else 0
        assignment.selection_reason = "再テスト不正解のため再学習" if becomes_target else "再テスト正答のため再学習対象外"
    participant.current_step = "final_test" if all_correct else "learning_targets"
    db.commit()
    return {
        "status": "completed",
        "next_step": participant.current_step,
        "next_url": "/final-test" if all_correct else "/learning-targets",
        "all_correct": all_correct,
        "retest_cycle_id": cycle.id,
        "relearning_target_count": cycle.relearning_target_count,
    }


async def score_final_test(db: Session, participant_id: str) -> dict[str, Any]:
    participant = get_participant(db, participant_id)
    attempts = _latest_attempts_by_term(db, participant.id, "final_test")
    if len(attempts) < 5:
        raise HTTPException(status_code=400, detail="final_test requires all five concept attempts")
    _score_test_attempts(db, participant, attempts, "final_test")
    participant.current_step = "finish"
    participant.completed_at = now()
    db.commit()
    recalculate_evaluation(db, participant.id)
    return {"status": "completed", "next_step": "finish", "next_url": "/finish"}


async def score_phase(db: Session, participant_id: str, phase: str) -> dict[str, Any]:
    if phase == "retest":
        return await score_retest(db, participant_id)
    if phase == "final_test":
        return await score_final_test(db, participant_id)
    participant = get_participant(db, participant_id)
    attempts = db.query(Attempt).filter_by(participant_id=participant.id, phase=phase).all()
    if not attempts:
        raise HTTPException(status_code=400, detail=f"{phase} attempts not found")
    for attempt in attempts:
        question = db.get(Question, attempt.question_id)
        option = _selected_option(db, attempt)
        if not option:
            raise HTTPException(status_code=400, detail=f"{phase} requires a selected option")
        attempt.is_correct = option.is_correct
        attempt.score = 1.0 if option.is_correct else 0.0
        attempt.diagnosed_status = "resolved" if option.is_correct else ("unknown" if option.misconception_type == "unknown" else "misconception")
        attempt.misconception_type = None if option.is_correct else option.misconception_type
        attempt.secondary_misconception_type = None
        attempt.l0_success = option.is_correct if phase == "l0_check" else None
        attempt.transfer_success = option.is_correct if phase == "transfer" else None
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
            previous_observation = _latest_observation(db, participant.id, attempt.term_id, None)
            retest_status = "resolved" if attempt.is_correct else ("unknown" if attempt.misconception_type == "unknown" else "misconception")
            observation = MisconceptionObservation(
                participant_id=participant.id,
                term_id=attempt.term_id,
                source_phase="retest",
                source_attempt_type="test",
                source_attempt_id=attempt.id,
                diagnosed_status=retest_status,
                primary_misconception_type=None if attempt.is_correct else attempt.misconception_type,
                secondary_misconception_type=attempt.secondary_misconception_type,
                diagnosis_confidence=1.0,
                diagnosis_evidence=option.body if option else attempt.free_text_answer,
                previous_status=previous_observation.diagnosed_status if previous_observation else state.current_status,
                previous_misconception_type=previous_observation.primary_misconception_type if previous_observation else state.primary_misconception,
                resolution_stage="confirmed_by_retest" if attempt.is_correct else "none",
                transition_type="resolution" if attempt.is_correct else ("recurrence" if attempt.recurrence_flag else "retest_change"),
                is_recurrence=attempt.recurrence_flag,
                standard_strategy=strategy_for(attempt.misconception_type, retest_status, participant.group_condition),
                applied_strategy=strategy_for(attempt.misconception_type, retest_status, participant.group_condition),
            )
            db.add(observation)
            db.flush()
            state.resolution_stage = observation.resolution_stage
            state.latest_observation_id = observation.id
        if phase == "l0_check":
            state.l0_success_count += 1 if attempt.is_correct else 0
            state.scaffolding_level = "L0" if attempt.is_correct else raise_level("L0")
        if phase == "transfer":
            state.transfer_success_count += 1 if attempt.is_correct else 0
            if not attempt.is_correct:
                attempt.misconception_type = "M4"
        state.current_status = "resolved" if phase == "retest" and attempt.is_correct else ("stable_correct" if attempt.is_correct else "misconception")
        state.primary_misconception = None if attempt.is_correct else attempt.misconception_type
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
    by_phase = {phase: [a for a in attempts if a.phase == phase] for phase in ["initial_test", "retest", "final_test", "l0_check", "transfer"]}
    initial_m = [a for a in by_phase["initial_test"] if a.misconception_type in {"M1", "M2", "M3"}]
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
    completed_sessions = [session for session in learning_sessions if session.status == "completed"]
    concept_attempts = db.query(ConceptUnderstandingAttempt).filter(ConceptUnderstandingAttempt.learning_session_id.in_(session_ids)).all() if session_ids else []
    phase1_attempts = [attempt for attempt in concept_attempts if attempt.concept_phase == "phase1"]
    phase2_attempts = [attempt for attempt in concept_attempts if attempt.concept_phase == "phase2"]
    phase1_attempted_session_ids = {attempt.learning_session_id for attempt in phase1_attempts}
    phase1_pass_session_ids = {attempt.learning_session_id for attempt in phase1_attempts if attempt.is_passed}
    phase2_attempted_session_ids = {attempt.learning_session_id for attempt in phase2_attempts}
    phase2_pass_session_ids = {attempt.learning_session_id for attempt in phase2_attempts if attempt.is_passed}
    phase2_retry_sessions = [session for session in learning_sessions if session.phase2_retry_count > 0]
    phase2_max_retry_sessions = [session for session in learning_sessions if session.concept_phase2_attempt_count >= PHASE2_ATTEMPT_LIMIT]
    retest_by_term_id = {attempt.term_id: attempt for attempt in _latest_attempts_by_term(db, participant.id, "retest")}
    final_by_term_id = {attempt.term_id: attempt for attempt in _latest_attempts_by_term(db, participant.id, "final_test")}
    initial_by_term_id = {attempt.term_id: attempt for attempt in _latest_attempts_by_term(db, participant.id, "initial_test")}
    retest_cycles = db.query(RetestCycle).filter_by(participant_id=participant.id).order_by(RetestCycle.cycle_index).all()
    first_cycle = retest_cycles[0] if retest_cycles else None
    first_cycle_results = db.query(RetestCycleResult).filter_by(retest_cycle_id=first_cycle.id).all() if first_cycle else []
    target_term_ids = {
        row.term_id
        for row in db.query(TermAssignment)
        .filter_by(participant_id=participant.id, is_learning_target=True)
        .all()
    }
    target_retests = [attempt for attempt in retest_by_term_id.values() if attempt.term_id in target_term_ids]
    non_target_retests = [attempt for attempt in retest_by_term_id.values() if attempt.term_id not in target_term_ids]
    choice_attempts = (
        db.query(LearningChoiceAttempt)
        .filter(LearningChoiceAttempt.learning_session_id.in_(session_ids))
        .order_by(LearningChoiceAttempt.created_at)
        .all()
        if session_ids
        else []
    )
    prerequisite_choice_attempts = [row for row in choice_attempts if row.stage == "prerequisite"]
    phase1_choice_attempts = [row for row in choice_attempts if row.stage == "concept_phase1"]
    phase2_choice_attempts = [row for row in choice_attempts if row.stage == "concept_phase2"]

    def by_slot(rows: list[LearningChoiceAttempt]) -> dict[tuple[str, str], list[LearningChoiceAttempt]]:
        grouped: dict[tuple[str, str], list[LearningChoiceAttempt]] = {}
        for row in rows:
            grouped.setdefault((row.learning_session_id, row.slot_key), []).append(row)
        return grouped

    prerequisite_slots = by_slot(prerequisite_choice_attempts)
    first_wrong_slots = [rows for rows in prerequisite_slots.values() if rows and not rows[0].is_correct]
    phase1_sessions_with_attempts = {row.learning_session_id for row in phase1_choice_attempts}
    phase1_sessions_with_forced = {
        row.learning_session_id for row in phase1_choice_attempts if row.result_status == "forced_resolved"
    }
    phase2_session_rows = by_slot(phase2_choice_attempts)
    phase2_first_wrong_sessions = {
        session_id for (session_id, _), rows in phase2_session_rows.items() if rows and not rows[0].is_correct
    }
    phase2_recovered_sessions = {
        session_id
        for (session_id, _), rows in phase2_session_rows.items()
        if rows and not rows[0].is_correct and any(row.is_correct for row in rows[1:])
    }
    phase2_pass_sessions = [session for session in learning_sessions if session.id in phase2_pass_session_ids]
    phase2_fail_sessions = [session for session in learning_sessions if session.status == "failed_phase2"]
    learning_observations = (
        db.query(MisconceptionObservation)
        .filter(
            MisconceptionObservation.participant_id == participant.id,
            MisconceptionObservation.source_phase.in_(["prerequisite", "concept_phase1", "concept_phase2"]),
            MisconceptionObservation.is_manual_override.is_(False),
        )
        .order_by(MisconceptionObservation.created_at)
        .all()
    )
    misconception_observations = [item for item in learning_observations if item.primary_misconception_type in {"M1", "M2", "M3"}]

    def learning_resolution_rate(mtype: str) -> float | None:
        affected_terms = {item.term_id for item in misconception_observations if item.primary_misconception_type == mtype}
        if not affected_terms:
            return None
        resolved_terms = {
            item.term_id
            for item in learning_observations
            if item.term_id in affected_terms and item.diagnosed_status == "resolved"
        }
        return len(resolved_terms) / len(affected_terms)

    support_events = (
        db.query(AdaptiveSupportEvent)
        .filter(AdaptiveSupportEvent.learning_session_id.in_(session_ids))
        .order_by(AdaptiveSupportEvent.created_at)
        .all()
        if session_ids
        else []
    )
    support_successes = 0
    for support in support_events:
        source = db.get(MisconceptionObservation, support.misconception_observation_id)
        if not source:
            continue
        next_observation = (
            db.query(MisconceptionObservation)
            .filter(
                MisconceptionObservation.learning_session_id == source.learning_session_id,
                MisconceptionObservation.prerequisite_term_id == source.prerequisite_term_id,
                MisconceptionObservation.created_at > source.created_at,
            )
            .order_by(MisconceptionObservation.created_at)
            .first()
        )
        if next_observation and next_observation.diagnosed_status == "resolved":
            support_successes += 1
    phase2_recurrences = [item for item in learning_observations if item.source_phase == "concept_phase2" and item.is_recurrence]
    phase2_misconception_observations = [
        item for item in learning_observations if item.source_phase == "concept_phase2" and item.primary_misconception_type in {"M1", "M2", "M3"}
    ]
    resolved_phase2_terms = {item.term_id for item in learning_observations if item.source_phase == "concept_phase2" and item.diagnosed_status == "resolved"}
    resolved_retest_attempts = [retest_by_term_id[term_id] for term_id in resolved_phase2_terms if term_id in retest_by_term_id]

    def retest_correct_for_sessions(sessions: list[LearningSession]) -> float | None:
        if not sessions:
            return None
        correct_count = 0
        for session in sessions:
            retest_attempt = retest_by_term_id.get(session.term_id)
            if retest_attempt and retest_attempt.is_correct:
                correct_count += 1
        return correct_count / len(sessions)

    summary = EvaluationSummary(
        participant_id=participant.id,
        group_condition=participant.group_condition,
        pretest_score=_rate(list(initial_by_term_id.values()), lambda a: bool(a.is_correct)),
        retest_score=_rate(list(retest_by_term_id.values()), lambda a: bool(a.is_correct)),
        initial_test_score_all_terms=_rate(list(initial_by_term_id.values()), lambda a: bool(a.is_correct)),
        first_retest_score_all_terms=(
            sum(1 for item in first_cycle_results if item.is_correct) / len(first_cycle_results)
            if first_cycle_results
            else None
        ),
        initial_to_first_retest_gain=(
            (sum(1 for item in first_cycle_results if item.is_correct) / len(first_cycle_results))
            - _rate(list(initial_by_term_id.values()), lambda a: bool(a.is_correct))
            if first_cycle_results and _rate(list(initial_by_term_id.values()), lambda a: bool(a.is_correct)) is not None
            else None
        ),
        retest_loop_count=len(retest_cycles) if retest_cycles else None,
        retest_relearning_target_count=sum(cycle.relearning_target_count for cycle in retest_cycles) if retest_cycles else None,
        final_test_score_all_terms=_rate(list(final_by_term_id.values()), lambda a: bool(a.is_correct)),
        initial_to_final_m_transition=(
            sum(
                1
                for term_id, initial in initial_by_term_id.items()
                if initial.misconception_type in {"M1", "M2", "M3"}
                and final_by_term_id.get(term_id)
                and final_by_term_id[term_id].misconception_type != initial.misconception_type
            )
            / len([a for a in initial_by_term_id.values() if a.misconception_type in {"M1", "M2", "M3"}])
            if [a for a in initial_by_term_id.values() if a.misconception_type in {"M1", "M2", "M3"}]
            else None
        ),
        retest_error_m_transition=(
            sum(1 for item in first_cycle_results if item.misconception_type in {"M1", "M2", "M3"} and final_by_term_id.get(item.term_id) and final_by_term_id[item.term_id].misconception_type != item.misconception_type)
            / len([item for item in first_cycle_results if item.misconception_type in {"M1", "M2", "M3"}])
            if [item for item in first_cycle_results if item.misconception_type in {"M1", "M2", "M3"}]
            else None
        ),
        pretest_score_all_terms=_rate(list(initial_by_term_id.values()), lambda a: bool(a.is_correct)),
        retest_score_all_terms=_rate(list(retest_by_term_id.values()), lambda a: bool(a.is_correct)),
        learning_target_retest_score=_rate(target_retests, lambda a: bool(a.is_correct)),
        non_target_retest_retention_rate=_rate(non_target_retests, lambda a: bool(a.is_correct)),
        l0_correct_rate=_rate(by_phase["l0_check"], lambda a: bool(a.l0_success)),
        transfer_correct_rate=_rate(by_phase["transfer"], lambda a: bool(a.transfer_success)),
        same_misconception_recurrence_rate=(len(same_rec) / len(initial_m)) if initial_m else None,
        m1_recurrence_rate=m_rate("M1"),
        m2_recurrence_rate=m_rate("M2"),
        m3_recurrence_rate=m_rate("M3"),
        m4_failure_rate=_rate(by_phase["transfer"], lambda a: a.misconception_type == "M4"),
        unknown_persistence_rate=None,
        prerequisite_pass_rate=(
            sum(1 for rows in prerequisite_slots.values() if any(row.is_correct for row in rows)) / len(prerequisite_slots)
            if prerequisite_slots
            else _rate(prerequisites, lambda p: p.status == "passed")
        ),
        prerequisite_required_question_accuracy=(
            sum(1 for rows in prerequisite_slots.values() if any(row.is_correct for row in rows)) / len(prerequisite_slots)
            if prerequisite_slots
            else None
        ),
        prerequisite_first_attempt_accuracy=(
            sum(1 for rows in prerequisite_slots.values() if rows[0].is_correct) / len(prerequisite_slots)
            if prerequisite_slots
            else None
        ),
        prerequisite_retry_recovery_rate=(
            sum(1 for rows in first_wrong_slots if any(row.is_correct for row in rows[1:])) / len(first_wrong_slots)
            if first_wrong_slots
            else None
        ),
        prerequisite_forced_resolution_rate=(
            sum(1 for rows in prerequisite_slots.values() if any(row.result_status == "forced_resolved" for row in rows))
            / len(prerequisite_slots)
            if prerequisite_slots
            else None
        ),
        concept_pass_rate=(len(completed_sessions) / len(learning_sessions)) if learning_sessions else None,
        concept_phase1_pass_rate=(
            sum(
                1
                for session_id in phase1_sessions_with_attempts
                if any(row.is_correct for row in phase1_choice_attempts if row.learning_session_id == session_id)
            )
            / len(phase1_sessions_with_attempts)
            if phase1_sessions_with_attempts
            else None
        ),
        phase1_all_questions_pass_rate=(
            sum(
                1
                for session_id in phase1_sessions_with_attempts
                if session_id not in phase1_sessions_with_forced
            )
            / len(phase1_sessions_with_attempts)
            if phase1_sessions_with_attempts
            else None
        ),
        phase1_forced_resolution_rate=(
            len(phase1_sessions_with_forced) / len(phase1_sessions_with_attempts)
            if phase1_sessions_with_attempts
            else None
        ),
        concept_phase2_success_rate=(
            len({row.learning_session_id for row in phase2_choice_attempts if row.is_correct})
            / len({row.learning_session_id for row in phase2_choice_attempts})
            if phase2_choice_attempts
            else None
        ),
        no_material_concept_discrimination_accuracy=(
            sum(1 for row in phase2_choice_attempts if row.is_correct) / len(phase2_choice_attempts)
            if phase2_choice_attempts
            else None
        ),
        phase2_after_retry_success_rate=(
            len(phase2_recovered_sessions) / len(phase2_first_wrong_sessions)
            if phase2_first_wrong_sessions
            else None
        ),
        phase2_max_retry_rate=(
            len(
                {
                    row.learning_session_id
                    for row in phase2_choice_attempts
                    if sum(1 for item in phase2_choice_attempts if item.learning_session_id == row.learning_session_id) >= 3
                }
            )
            / len({row.learning_session_id for row in phase2_choice_attempts})
            if phase2_choice_attempts
            else None
        ),
        phase2_forced_completion_rate=(
            sum(1 for session in learning_sessions if session.group_condition == "proposed" and session.phase2_forced_completion)
            / sum(1 for session in learning_sessions if session.group_condition == "proposed" and session.id in {row.learning_session_id for row in phase2_choice_attempts})
            if any(session.group_condition == "proposed" and session.id in {row.learning_session_id for row in phase2_choice_attempts} for session in learning_sessions)
            else None
        ),
        phase2_pass_retest_correct_rate=retest_correct_for_sessions(phase2_pass_sessions),
        phase2_fail_retest_correct_rate=retest_correct_for_sessions(phase2_fail_sessions),
        learning_misconception_persistence_rate=(
            sum(1 for item in misconception_observations if item.is_persistence) / len(misconception_observations)
            if misconception_observations
            else None
        ),
        m1_resolution_rate=learning_resolution_rate("M1"),
        m2_resolution_rate=learning_resolution_rate("M2"),
        m3_resolution_rate=learning_resolution_rate("M3"),
        strategy_next_response_success_rate=(support_successes / len(support_events)) if support_events else None,
        phase2_misconception_recurrence_rate=(
            len(phase2_recurrences) / len(phase2_misconception_observations)
            if phase2_misconception_observations
            else None
        ),
        learning_resolved_retest_correct_rate=_rate(resolved_retest_attempts, lambda item: bool(item.is_correct)),
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
                "initial_test_score_all_terms": avg("initial_test_score_all_terms"),
                "first_retest_score_all_terms": avg("first_retest_score_all_terms"),
                "initial_to_first_retest_gain": avg("initial_to_first_retest_gain"),
                "retest_loop_count": avg("retest_loop_count"),
                "retest_relearning_target_count": avg("retest_relearning_target_count"),
                "final_test_score_all_terms": avg("final_test_score_all_terms"),
                "initial_to_final_m_transition": avg("initial_to_final_m_transition"),
                "retest_error_m_transition": avg("retest_error_m_transition"),
                "pretest_score": avg("pretest_score"),
                "retest_score": avg("retest_score"),
                "pretest_score_all_terms": avg("pretest_score_all_terms"),
                "retest_score_all_terms": avg("retest_score_all_terms"),
                "learning_target_retest_score": avg("learning_target_retest_score"),
                "non_target_retest_retention_rate": avg("non_target_retest_retention_rate"),
                "same_misconception_recurrence_rate": avg("same_misconception_recurrence_rate"),
                "l0_correct_rate": avg("l0_correct_rate"),
                "transfer_correct_rate": avg("transfer_correct_rate"),
                "prerequisite_pass_rate": avg("prerequisite_pass_rate"),
                "prerequisite_required_question_accuracy": avg("prerequisite_required_question_accuracy"),
                "prerequisite_forced_resolution_rate": avg("prerequisite_forced_resolution_rate"),
                "concept_pass_rate": avg("concept_pass_rate"),
                "concept_phase1_pass_rate": avg("concept_phase1_pass_rate"),
                "concept_phase2_success_rate": avg("concept_phase2_success_rate"),
                "no_material_concept_discrimination_accuracy": avg("no_material_concept_discrimination_accuracy"),
                "phase2_after_retry_success_rate": avg("phase2_after_retry_success_rate"),
                "phase2_forced_completion_rate": avg("phase2_forced_completion_rate"),
                "phase2_max_retry_rate": avg("phase2_max_retry_rate"),
                "phase2_pass_retest_correct_rate": avg("phase2_pass_retest_correct_rate"),
                "phase2_fail_retest_correct_rate": avg("phase2_fail_retest_correct_rate"),
                "learning_misconception_persistence_rate": avg("learning_misconception_persistence_rate"),
                "strategy_next_response_success_rate": avg("strategy_next_response_success_rate"),
                "phase2_misconception_recurrence_rate": avg("phase2_misconception_recurrence_rate"),
            }
        )
    return {"groups": rows}


def admin_diagnoses(db: Session) -> dict[str, Any]:
    rows = (
        db.query(MisconceptionObservation, Participant, Term)
        .join(Participant, MisconceptionObservation.participant_id == Participant.id)
        .join(Term, MisconceptionObservation.term_id == Term.id)
        .order_by(MisconceptionObservation.created_at.desc())
        .limit(500)
        .all()
    )
    return {
        "diagnoses": [
            {
                "observation_id": observation.id,
                "participant_id": participant.id,
                "display_code": participant.display_code,
                "participant_completed": participant.completed_at is not None,
                "term_label": term.label,
                "source_phase": observation.source_phase,
                "diagnosed_status": observation.diagnosed_status,
                "primary_misconception_type": observation.primary_misconception_type,
                "secondary_misconception_type": observation.secondary_misconception_type,
                "diagnosis_confidence": observation.diagnosis_confidence,
                "diagnosis_evidence": observation.diagnosis_evidence,
                "transition_type": observation.transition_type,
                "applied_strategy": observation.applied_strategy,
                "requires_manual_review": observation.requires_manual_review,
                "is_manual_override": observation.is_manual_override,
                "created_at": observation.created_at.isoformat(),
            }
            for observation, participant, term in rows
        ]
    }


def override_diagnosis(
    db: Session,
    observation_id: str,
    payload: dict[str, Any],
) -> MisconceptionObservation:
    original = db.get(MisconceptionObservation, observation_id)
    if not original:
        raise HTTPException(status_code=404, detail="diagnosis observation not found")
    participant = get_participant(db, original.participant_id)
    if participant.completed_at is None:
        raise HTTPException(status_code=409, detail="manual override is allowed only after experiment completion")
    status = payload["diagnosed_status"]
    primary = payload.get("primary_misconception_type")
    if status == "resolved":
        primary = None
    if status == "unknown":
        primary = "unknown"
    standard = strategy_for(primary, status, "proposed")
    override = MisconceptionObservation(
        participant_id=original.participant_id,
        term_id=original.term_id,
        learning_session_id=original.learning_session_id,
        prerequisite_term_id=original.prerequisite_term_id,
        source_phase=original.source_phase,
        source_attempt_type="manual_override",
        source_attempt_id=original.source_attempt_id,
        diagnosed_status=status,
        primary_misconception_type=primary,
        secondary_misconception_type=payload.get("secondary_misconception_type"),
        diagnosis_confidence=1.0,
        diagnosis_evidence=payload.get("diagnosis_evidence") or original.diagnosis_evidence,
        previous_status=original.diagnosed_status,
        previous_misconception_type=original.primary_misconception_type,
        resolution_stage=payload.get("resolution_stage") or ("confirmed_by_retest" if status == "resolved" else "none"),
        transition_type="manual_override",
        standard_strategy=standard,
        applied_strategy=standard,
        requires_manual_review=False,
        is_manual_override=True,
        overrides_observation_id=original.id,
    )
    db.add(override)
    db.flush()
    if original.source_attempt_id and original.source_phase in {"initial_test", "retest", "final_test"}:
        attempt = db.get(Attempt, original.source_attempt_id)
        if attempt:
            attempt.diagnosed_status = "stable_correct" if status == "resolved" else status
            attempt.misconception_type = primary
            attempt.secondary_misconception_type = payload.get("secondary_misconception_type")
            attempt.misconception_confidence = 1.0
            attempt.natural_language_diagnosis = payload.get("diagnosis_evidence") or original.diagnosis_evidence
            attempt.is_correct = status == "resolved"
            attempt.score = 1.0 if status == "resolved" else 0.0
    if original.prerequisite_term_id:
        prereq = db.get(PrerequisiteTerm, original.prerequisite_term_id)
        if prereq:
            prereq.current_status = override.diagnosed_status
            prereq.primary_misconception_type = override.primary_misconception_type
            prereq.secondary_misconception_type = override.secondary_misconception_type
            prereq.resolution_stage = override.resolution_stage
            prereq.latest_observation_id = override.id
    else:
        state = db.query(LearnerState).filter_by(participant_id=original.participant_id, term_id=original.term_id).one_or_none()
        if state:
            state.current_status = override.diagnosed_status
            state.primary_misconception = override.primary_misconception_type
            state.secondary_misconception = override.secondary_misconception_type
            state.resolution_stage = override.resolution_stage
            state.latest_observation_id = override.id
    db.add(
        AuditEvent(
            actor=payload.get("actor") or "researcher",
            action="override_diagnosis",
            entity_type="misconception_observation",
            entity_id=override.id,
            before_json={
                "observation_id": original.id,
                "diagnosed_status": original.diagnosed_status,
                "primary_misconception_type": original.primary_misconception_type,
            },
            after_json={
                "diagnosed_status": override.diagnosed_status,
                "primary_misconception_type": override.primary_misconception_type,
                "reason": payload["reason"],
            },
        )
    )
    initial_by_term = {
        item.term_id: item
        for item in db.query(Attempt).filter_by(participant_id=participant.id, phase="initial_test").all()
    }
    for retest_attempt in db.query(Attempt).filter_by(participant_id=participant.id, phase="retest").all():
        pretest_attempt = initial_by_term.get(retest_attempt.term_id)
        retest_attempt.recurrence_flag = bool(
            pretest_attempt
            and pretest_attempt.misconception_type in {"M1", "M2", "M3"}
            and pretest_attempt.misconception_type == retest_attempt.misconception_type
        )
    db.commit()
    recalculate_evaluation(db, participant.id)
    return override


EXPORTS = {
    "participants": (Participant, ["id", "display_code", "group_condition", "assignment_method", "content_version_id", "current_step", "started_at", "completed_at"]),
    "content_versions": (ContentVersion, ["id", "content_type", "version_key", "source_file", "file_hash", "validation_status", "is_active", "imported_at"]),
    "prerequisite_definitions": (PrerequisiteDefinition, ["id", "content_version_id", "target_term_id", "prerequisite_key", "label", "display_order", "set_version", "is_active"]),
    "learning_question_slots": (LearningQuestionSlot, ["id", "content_version_id", "target_term_id", "prerequisite_definition_id", "stage", "slot_key", "required_order", "cycle_index"]),
    "learning_questions": (LearningQuestion, ["id", "slot_id", "learning_session_id", "variant_key", "attempt_index", "body", "source_type", "validation_status", "is_active", "generated_at"]),
    "learning_question_options": (LearningQuestionOption, ["id", "learning_question_id", "body", "is_correct", "misconception_type", "diagnostic_rationale", "linked_prerequisite_keys", "remediation_focus", "default_order"]),
    "learning_question_display_orders": (LearningQuestionDisplayOrder, ["id", "participant_id", "learning_question_id", "option_order", "random_seed", "created_at"]),
    "participant_surveys": (ParticipantSurvey, ["id", "participant_id", "phase", "ai_experience_level", "programming_experience_level", "llm_usage_level", "self_rated_ai_knowledge", "term_confidences", "free_comment"]),
    "term_assignments": (TermAssignment, ["id", "participant_id", "term_id", "group_condition", "is_learning_target", "selection_reason", "priority_score", "created_at"]),
    "attempts": (Attempt, ["id", "participant_id", "term_id", "phase", "question_id", "selected_option_id", "reason_text", "free_text_answer", "confidence", "is_correct", "score", "diagnosed_status", "misconception_type", "recurrence_flag", "l0_success", "transfer_success", "requires_manual_review", "created_at"]),
    "learner_states": (LearnerState, ["participant_id", "term_id", "current_status", "primary_misconception", "secondary_misconception", "resolution_stage", "latest_observation_id", "scaffolding_level", "teaching_strategy", "stable_correct_count", "recurrence_count", "l0_success_count", "transfer_success_count", "updated_at"]),
    "learning_sessions": (LearningSession, ["id", "participant_id", "term_id", "group_condition", "session_index", "learning_cycle_index", "triggered_by_retest_cycle_id", "is_relearning_session", "content_version_id", "prerequisite_set_version", "status", "current_stage", "current_prerequisite_key", "current_slot_key", "current_attempt_index", "current_cycle_index", "phase2_forced_completion", "technical_block_reason", "completed_at", "created_at"]),
    "learning_session_prerequisites": (LearningSessionPrerequisite, ["id", "learning_session_id", "prerequisite_definition_id", "prerequisite_key", "label", "display_order", "status", "completed_slot_count", "forced_slot_count", "review_count", "created_at"]),
    "generated_learning_materials": (GeneratedLearningMaterial, ["id", "participant_id", "learning_session_id", "target_term_id", "prerequisite_definition_id", "stage", "material_mode", "cycle_index", "slot_key", "attempt_index", "group_condition", "diagnosis_snapshot", "rag_context", "material", "examples", "comparisons", "counterexamples", "rag_sources", "general_knowledge_supplement", "answer_leak_detected", "regeneration_count", "ai_call_log_id", "created_at"]),
    "learning_choice_attempts": (LearningChoiceAttempt, ["id", "participant_id", "learning_session_id", "target_term_id", "prerequisite_definition_id", "stage", "slot_key", "question_id", "selected_option_id", "displayed_option_order", "cycle_index", "attempt_index", "is_correct", "misconception_type", "transition_type", "is_persistence", "is_recurrence", "result_status", "forced_answer_shown", "response_time_sec", "material_id", "feedback_text", "idempotency_key", "created_at"]),
    "prerequisite_terms": (PrerequisiteTerm, ["id", "learning_session_id", "term_label", "generation_reason", "display_order", "status", "attempt_count", "current_status", "primary_misconception_type", "secondary_misconception_type", "resolution_stage", "teaching_strategy", "latest_observation_id", "last_feedback", "created_at"]),
    "term_understanding_attempts": (TermUnderstandingAttempt, ["id", "prerequisite_term_id", "participant_id", "learning_session_id", "attempt_index", "attempt_kind", "counts_toward_limit", "clarification_parent_attempt_id", "presented_question", "learner_answer", "is_passed", "score", "primary_misconception_type", "secondary_misconception_type", "diagnosis_observation_id", "feedback", "created_at"]),
    "concept_understanding_attempts": (ConceptUnderstandingAttempt, ["id", "learning_session_id", "participant_id", "attempt_index", "concept_phase", "phase1_cycle_index", "attempt_kind", "counts_toward_limit", "clarification_parent_attempt_id", "presented_question", "material_shown", "light_condition_text", "learner_answer", "is_passed", "score", "primary_misconception_type", "secondary_misconception_type", "diagnosis_observation_id", "feedback", "independent_explanation_success", "return_to_phase1", "rubric_scores", "missing_prerequisite_ids", "review_prerequisite_ids", "created_at"]),
    "tutor_sessions": (TutorSession, ["id", "participant_id", "term_id", "session_index", "group_condition", "started_at", "ended_at"]),
    "tutor_turns": (TutorTurn, ["id", "tutor_session_id", "turn_index", "scaffolding_level", "teaching_strategy", "strategy_changed", "tutor_message", "learner_response", "ai_feedback", "next_scaffolding_level", "forbidden_help_given", "created_at"]),
    "recurrence_events": (RecurrenceEvent, ["id", "participant_id", "term_id", "previous_attempt_id", "current_attempt_id", "previous_misconception_type", "current_misconception_type", "is_same_type", "phase", "created_at"]),
    "retest_cycles": (RetestCycle, ["id", "participant_id", "cycle_index", "status", "all_correct", "relearning_target_count", "started_at", "completed_at", "created_at"]),
    "retest_cycle_results": (RetestCycleResult, ["id", "retest_cycle_id", "participant_id", "term_id", "attempt_id", "is_correct", "misconception_type", "becomes_learning_target", "created_at"]),
    "ai_call_logs": (AICallLog, ["id", "provider", "fallback_provider", "purpose", "status", "error_code", "latency_ms", "created_at"]),
    "misconception_observations": (MisconceptionObservation, ["id", "participant_id", "term_id", "learning_session_id", "prerequisite_term_id", "source_phase", "source_attempt_type", "source_attempt_id", "diagnosed_status", "primary_misconception_type", "secondary_misconception_type", "diagnosis_confidence", "diagnosis_evidence", "previous_status", "previous_misconception_type", "resolution_stage", "transition_type", "is_persistence", "is_recurrence", "standard_strategy", "applied_strategy", "strategy_override_reason", "requires_manual_review", "is_manual_override", "overrides_observation_id", "created_at"]),
    "adaptive_support_events": (AdaptiveSupportEvent, ["id", "misconception_observation_id", "learning_session_id", "mode", "feedback", "supplemental_material", "next_check_question", "diagnostic_focus", "rag_sources", "general_knowledge_supplement", "ai_call_log_id", "created_at"]),
    "evaluation_summary": (EvaluationSummary, ["participant_id", "group_condition", "initial_test_score_all_terms", "first_retest_score_all_terms", "initial_to_first_retest_gain", "retest_loop_count", "retest_relearning_target_count", "final_test_score_all_terms", "initial_to_final_m_transition", "retest_error_m_transition", "prerequisite_required_question_accuracy", "prerequisite_first_attempt_accuracy", "prerequisite_retry_recovery_rate", "prerequisite_forced_resolution_rate", "phase1_all_questions_pass_rate", "phase1_forced_resolution_rate", "learning_target_count", "completed", "created_at"]),
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
