from __future__ import annotations

import random
import re
from difflib import SequenceMatcher
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    ContentVersion,
    GeneratedLearningMaterial,
    LearnerState,
    LearningChoiceAttempt,
    LearningQuestion,
    LearningQuestionDisplayOrder,
    LearningQuestionOption,
    LearningQuestionSlot,
    LearningSession,
    LearningSessionPrerequisite,
    Participant,
    PrerequisiteDefinition,
    Term,
    now,
)
from app.services.experiment import (
    _ai_call,
    _current_learning_cycle_index,
    _initial_test_context,
    _latest_retest_context,
    _learning_rag_context,
    get_participant,
)


MAX_SLOT_ATTEMPTS = 3
MAX_PHASE2_ATTEMPTS = 3


def _participant_release(db: Session, participant: Participant) -> ContentVersion:
    release = db.get(ContentVersion, participant.content_version_id) if participant.content_version_id else None
    if not release:
        release = (
            db.query(ContentVersion)
            .filter_by(content_type="experiment_release", is_active=True)
            .order_by(ContentVersion.imported_at.desc())
            .first()
        )
        if not release:
            raise HTTPException(status_code=503, detail="active experiment content is not available")
        participant.content_version_id = release.id
        db.commit()
    return release


def _term(db: Session, term_slug: str) -> Term:
    term = db.query(Term).filter_by(slug=term_slug, is_active=True).one_or_none()
    if not term:
        raise HTTPException(status_code=404, detail="term not found")
    return term


def _definitions(db: Session, session: LearningSession) -> list[PrerequisiteDefinition]:
    return (
        db.query(PrerequisiteDefinition)
        .filter_by(
            content_version_id=session.content_version_id,
            target_term_id=session.term_id,
            is_active=True,
        )
        .order_by(PrerequisiteDefinition.display_order)
        .all()
    )


def _definition_by_key(db: Session, session: LearningSession, key: str | None) -> PrerequisiteDefinition | None:
    if not key:
        return None
    return (
        db.query(PrerequisiteDefinition)
        .filter_by(
            content_version_id=session.content_version_id,
            target_term_id=session.term_id,
            prerequisite_key=key,
            is_active=True,
        )
        .one_or_none()
    )


def _slot(db: Session, session: LearningSession) -> LearningQuestionSlot:
    slot = (
        db.query(LearningQuestionSlot)
        .filter_by(
            content_version_id=session.content_version_id,
            target_term_id=session.term_id,
            slot_key=session.current_slot_key,
        )
        .one_or_none()
    )
    if not slot:
        raise HTTPException(status_code=409, detail="current learning question slot is missing")
    return slot


def _question_for_attempt(db: Session, slot: LearningQuestionSlot, attempt_index: int) -> LearningQuestion | None:
    return (
        db.query(LearningQuestion)
        .filter_by(slot_id=slot.id, attempt_index=attempt_index, is_active=True)
        .order_by(LearningQuestion.created_at)
        .first()
    )


def _question_options(db: Session, question_id: str) -> list[LearningQuestionOption]:
    return (
        db.query(LearningQuestionOption)
        .filter_by(learning_question_id=question_id)
        .order_by(LearningQuestionOption.default_order)
        .all()
    )


def _display_order(
    db: Session,
    participant_id: str,
    question: LearningQuestion,
) -> LearningQuestionDisplayOrder:
    row = (
        db.query(LearningQuestionDisplayOrder)
        .filter_by(participant_id=participant_id, learning_question_id=question.id)
        .one_or_none()
    )
    if row:
        return row
    option_ids = [option.id for option in _question_options(db, question.id)]
    seed = f"{get_settings().random_seed}:{participant_id}:{question.id}"
    rng = random.Random(seed)
    rng.shuffle(option_ids)
    row = LearningQuestionDisplayOrder(
        participant_id=participant_id,
        learning_question_id=question.id,
        option_order=option_ids,
        random_seed=seed,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _public_question(db: Session, participant_id: str, question: LearningQuestion) -> dict[str, Any]:
    order = _display_order(db, participant_id, question)
    options = {option.id: option for option in _question_options(db, question.id)}
    return {
        "question_id": question.id,
        "body": question.body,
        "options": [
            {
                "option_id": option_id,
                "label": chr(65 + index),
                "body": options[option_id].body,
            }
            for index, option_id in enumerate(order.option_order)
        ],
    }


def _history(db: Session, session: LearningSession) -> list[dict[str, Any]]:
    attempts = (
        db.query(LearningChoiceAttempt)
        .filter_by(learning_session_id=session.id)
        .order_by(LearningChoiceAttempt.created_at)
        .all()
    )
    return [
        {
            "stage": row.stage,
            "slot_key": row.slot_key,
            "attempt_index": row.attempt_index,
            "is_correct": row.is_correct,
            "misconception_type": row.misconception_type,
            "result_status": row.result_status,
        }
        for row in attempts[-20:]
    ]


def _material_payload(
    db: Session,
    session: LearningSession,
    stage: str,
    material_mode: str,
) -> dict[str, Any]:
    participant = get_participant(db, session.participant_id)
    term = db.get(Term, session.term_id)
    definition = _definition_by_key(db, session, session.current_prerequisite_key)
    payload: dict[str, Any] = {
        "participant_id": participant.id,
        "group_condition": participant.group_condition,
        "target_term": {"slug": term.slug, "label": term.label, "description": term.description},
        "material_mode": material_mode,
        "cycle_index": session.current_cycle_index,
        "rag_context": _learning_rag_context(
            term,
            definition.label if definition else "",
            stage,
            material_mode,
        ),
    }
    if definition:
        payload["fixed_prerequisite"] = {
            "key": definition.prerequisite_key,
            "label": definition.label,
        }
    if participant.group_condition == "proposed":
        payload["diagnosis_context"] = _initial_test_context(db, participant, term)
        payload["retest_context"] = _latest_retest_context(db, participant, term)
        payload["learning_history"] = _history(db, session)
    return payload


def _normalize(text: str) -> str:
    return re.sub(r"[\W_]+", "", text).lower()


def _answer_leak(db: Session, session: LearningSession, material: str) -> bool:
    normalized_material = _normalize(material)
    slots = (
        db.query(LearningQuestionSlot)
        .filter_by(content_version_id=session.content_version_id, target_term_id=session.term_id)
        .all()
    )
    slot_ids = [slot.id for slot in slots]
    if not slot_ids:
        return False
    questions = db.query(LearningQuestion).filter(LearningQuestion.slot_id.in_(slot_ids)).all()
    question_ids = [question.id for question in questions]
    correct_options = (
        db.query(LearningQuestionOption)
        .filter(
            LearningQuestionOption.learning_question_id.in_(question_ids),
            LearningQuestionOption.is_correct.is_(True),
        )
        .all()
    )
    for option in correct_options:
        answer = _normalize(option.body)
        if len(answer) < 20:
            continue
        match = SequenceMatcher(None, normalized_material, answer).find_longest_match()
        if answer in normalized_material or match.size >= 24 or SequenceMatcher(None, normalized_material, answer).ratio() >= 0.88:
            return True
    return False


async def _generate_material(
    db: Session,
    session: LearningSession,
    stage: str,
    material_mode: str,
) -> GeneratedLearningMaterial:
    payload = _material_payload(db, session, stage, material_mode)
    purpose = "generate_prerequisite_material" if stage in {"prerequisite", "prerequisite_review"} else "generate_concept_phase1_material"
    result: dict[str, Any] | None = None
    material = ""
    leak = False
    for regeneration_count in range(3):
        result = await _ai_call(db, purpose, payload)
        material = result.get("material") or result.get("concept_material") or ""
        leak = _answer_leak(db, session, material)
        if not leak:
            break
        payload["regeneration_reason"] = "answer_leak_detected"
    if result is None or not material or leak:
        session.status = "technical_blocked"
        session.technical_block_reason = "教材が未出題問題の正答文に近すぎるため生成を停止しました。"
        db.commit()
        raise HTTPException(status_code=503, detail=session.technical_block_reason)
    definition = _definition_by_key(db, session, session.current_prerequisite_key)
    row = GeneratedLearningMaterial(
        participant_id=session.participant_id,
        learning_session_id=session.id,
        target_term_id=session.term_id,
        prerequisite_definition_id=definition.id if definition else None,
        stage=stage,
        material_mode=material_mode,
        cycle_index=session.current_cycle_index,
        slot_key=session.current_slot_key,
        attempt_index=session.current_attempt_index,
        group_condition=session.group_condition,
        diagnosis_snapshot=payload.get("diagnosis_context"),
        rag_context=payload.get("rag_context"),
        material=material,
        examples=result.get("examples"),
        comparisons=result.get("comparisons"),
        counterexamples=result.get("counterexamples"),
        rag_sources=result.get("rag_sources"),
        general_knowledge_supplement=result.get("general_knowledge_supplement"),
        answer_leak_detected=False,
        regeneration_count=regeneration_count,
        ai_call_log_id=result.get("_ai_call_log_id"),
    )
    db.add(row)
    db.flush()
    session.current_material_id = row.id
    session.technical_block_reason = None
    session.status = session.current_stage or stage
    db.commit()
    db.refresh(row)
    return row


def _current_material(db: Session, session: LearningSession) -> GeneratedLearningMaterial | None:
    return db.get(GeneratedLearningMaterial, session.current_material_id) if session.current_material_id else None


async def _ensure_question_available(db: Session, session: LearningSession) -> LearningQuestion:
    slot = _slot(db, session)
    existing = _question_for_attempt(db, slot, session.current_attempt_index)
    if existing:
        return existing
    term = db.get(Term, session.term_id)
    definition = _definition_by_key(db, session, session.current_prerequisite_key)
    previous_questions = db.query(LearningQuestion).filter_by(slot_id=slot.id).all()
    payload: dict[str, Any] = {
        "participant_id": session.participant_id,
        "group_condition": session.group_condition,
        "target_term": {"slug": term.slug, "label": term.label, "description": term.description},
        "focus_label": definition.label if definition else term.label,
        "stage": session.current_stage,
        "slot_key": session.current_slot_key,
        "attempt_index": session.current_attempt_index,
        "existing_question_bodies": [row.body for row in previous_questions],
        "rag_context": _learning_rag_context(term, definition.label if definition else ""),
    }
    if session.group_condition == "proposed":
        participant = get_participant(db, session.participant_id)
        payload["diagnosis_context"] = _initial_test_context(db, participant, term)
        payload["retest_context"] = _latest_retest_context(db, participant, term)
        payload["learning_history"] = _history(db, session)
    result = await _ai_call(db, "generate_emergency_question_variant", payload)
    options = result.get("options") or []
    types = [item.get("misconception_type") for item in options]
    correct_count = sum(1 for item in options if item.get("is_correct"))
    body = result.get("body") or ""
    too_similar = any(SequenceMatcher(None, _normalize(body), _normalize(row.body)).ratio() >= 0.88 for row in previous_questions)
    if len(options) != 5 or correct_count != 1 or set(types) != {None, "M1", "M2", "M3", "unknown"} or too_similar:
        session.status = "technical_blocked"
        session.technical_block_reason = "AI追加問題が固定問題の検証条件を満たしませんでした。"
        db.commit()
        raise HTTPException(status_code=503, detail=session.technical_block_reason)
    question = LearningQuestion(
        slot_id=slot.id,
        learning_session_id=session.id,
        variant_key=f"runtime_{session.id}_{session.current_attempt_index}",
        attempt_index=session.current_attempt_index,
        body=body,
        source_type="runtime_ai_fallback",
        validation_status="runtime_validated",
        generated_at=now(),
    )
    db.add(question)
    db.flush()
    linked_default = [definition.prerequisite_key] if definition else [_definitions(db, session)[0].prerequisite_key]
    for order, item in enumerate(options):
        db.add(
            LearningQuestionOption(
                learning_question_id=question.id,
                body=item["body"],
                is_correct=bool(item["is_correct"]),
                misconception_type=item.get("misconception_type"),
                diagnostic_rationale="runtime validated emergency option",
                linked_prerequisite_keys=[] if item.get("is_correct") or item.get("misconception_type") == "unknown" else linked_default,
                remediation_focus=definition.label if definition else term.label,
                default_order=order,
            )
        )
    db.commit()
    return question


def _current_question(db: Session, session: LearningSession) -> LearningQuestion:
    question = _question_for_attempt(db, _slot(db, session), session.current_attempt_index)
    if not question:
        raise HTTPException(status_code=409, detail="question bank is exhausted")
    return question


def _slot_attempt_count(db: Session, session: LearningSession, slot_key: str) -> int:
    return (
        db.query(func.count(LearningChoiceAttempt.id))
        .filter_by(learning_session_id=session.id, slot_key=slot_key)
        .scalar()
        or 0
    )


def _session_prerequisite_rows(db: Session, session: LearningSession) -> list[LearningSessionPrerequisite]:
    return (
        db.query(LearningSessionPrerequisite)
        .filter_by(learning_session_id=session.id)
        .order_by(LearningSessionPrerequisite.display_order)
        .all()
    )


async def create_fixed_learning_session(
    db: Session,
    participant_id: str,
    term_slug: str,
) -> LearningSession:
    participant = get_participant(db, participant_id)
    release = _participant_release(db, participant)
    term = _term(db, term_slug)
    learning_cycle_index = _current_learning_cycle_index(db, participant.id)
    existing = (
        db.query(LearningSession)
        .filter_by(
            participant_id=participant.id,
            term_id=term.id,
            content_version_id=release.id,
            learning_cycle_index=learning_cycle_index,
        )
        .order_by(LearningSession.created_at.desc())
        .first()
    )
    if existing:
        return existing
    definitions = (
        db.query(PrerequisiteDefinition)
        .filter_by(content_version_id=release.id, target_term_id=term.id, is_active=True)
        .order_by(PrerequisiteDefinition.display_order)
        .all()
    )
    if not definitions:
        raise HTTPException(status_code=503, detail="fixed prerequisites are not available")
    count = db.query(func.count(LearningSession.id)).filter_by(participant_id=participant.id, term_id=term.id).scalar() or 0
    trigger_cycle = None
    if learning_cycle_index > 1:
        from app.models import RetestCycle

        trigger_cycle = (
            db.query(RetestCycle)
            .filter_by(participant_id=participant.id, cycle_index=learning_cycle_index - 1)
            .one_or_none()
        )
    session = LearningSession(
        participant_id=participant.id,
        term_id=term.id,
        group_condition=participant.group_condition,
        session_index=count + 1,
        status="prerequisite",
        content_version_id=release.id,
        prerequisite_set_version=definitions[0].set_version,
        learning_cycle_index=learning_cycle_index,
        triggered_by_retest_cycle_id=trigger_cycle.id if trigger_cycle else None,
        is_relearning_session=learning_cycle_index > 1,
        current_stage="prerequisite",
        current_prerequisite_key=definitions[0].prerequisite_key,
        current_slot_key=f"prerequisite:{definitions[0].prerequisite_key}:slot1",
        current_attempt_index=1,
        current_cycle_index=1,
    )
    db.add(session)
    db.flush()
    for definition in definitions:
        db.add(
            LearningSessionPrerequisite(
                learning_session_id=session.id,
                prerequisite_definition_id=definition.id,
                prerequisite_key=definition.prerequisite_key,
                label=definition.label,
                display_order=definition.display_order,
            )
        )
    db.commit()
    try:
        await _generate_material(db, session, "prerequisite", "initial")
        await _ensure_question_available(db, session)
    except HTTPException as exc:
        if exc.status_code != 503:
            raise
        session = db.get(LearningSession, session.id) or session
        session.status = "technical_blocked"
        session.technical_block_reason = (
            exc.detail.get("message")
            if isinstance(exc.detail, dict)
            else str(exc.detail or "教材生成に失敗しました。")
        )
        db.commit()
        db.refresh(session)
        return session
    return session


def fixed_learning_session_state(db: Session, session_id: str) -> dict[str, Any]:
    session = db.get(LearningSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="learning session not found")
    participant = get_participant(db, session.participant_id)
    term = db.get(Term, session.term_id)
    prereqs = _session_prerequisite_rows(db, session)
    current_definition = _definition_by_key(db, session, session.current_prerequisite_key)
    terminal = session.status in {"completed", "technical_blocked"}
    question = None if terminal else _current_question(db, session)
    material = _current_material(db, session)
    current_prereq_index = next(
        (index for index, row in enumerate(prereqs, start=1) if row.prerequisite_key == session.current_prerequisite_key),
        None,
    )
    slot_index = 1
    if session.current_slot_key and "slot2" in session.current_slot_key:
        slot_index = 2
    return {
        "learning_session_id": session.id,
        "participant_id": participant.id,
        "group_condition": participant.group_condition,
        "status": session.status,
        "stage": session.current_stage,
        "term_slug": term.slug,
        "term_label": term.label,
        "term_description": term.description,
        "content_version": db.get(ContentVersion, session.content_version_id).version_key,
        "progress": {
            "prerequisite_index": current_prereq_index,
            "prerequisite_total": len(prereqs),
            "required_question_index": slot_index if session.current_stage in {"prerequisite", "prerequisite_review", "concept_phase1"} else None,
            "required_question_total": 2 if session.current_stage in {"prerequisite", "prerequisite_review", "concept_phase1"} else 1,
            "attempt_index": session.current_attempt_index,
            "max_attempts": 1 if session.current_stage == "concept_phase2" and session.group_condition == "control" else 3,
            "cycle_index": session.current_cycle_index,
        },
        "current_prerequisite": None
        if not current_definition
        else {
            "key": current_definition.prerequisite_key,
            "label": current_definition.label,
        },
        "prerequisites": [
            {
                "key": row.prerequisite_key,
                "label": row.label,
                "display_order": row.display_order,
                "status": row.status,
                "completed_slot_count": row.completed_slot_count,
                "forced_slot_count": row.forced_slot_count,
                "review_count": row.review_count,
            }
            for row in prereqs
        ],
        "material": None
        if session.current_stage == "concept_phase2" or not material
        else {"material_id": material.id, "body": material.material},
        "question": None if not question else _public_question(db, participant.id, question),
        "last_feedback": session.last_feedback,
        "technical_block_reason": session.technical_block_reason,
    }


def _scope_attempts(db: Session, session: LearningSession, stage: str, prerequisite_id: str | None):
    query = db.query(LearningChoiceAttempt).filter_by(learning_session_id=session.id)
    if stage in {"prerequisite", "prerequisite_review"}:
        return query.filter_by(prerequisite_definition_id=prerequisite_id)
    return query.filter(LearningChoiceAttempt.stage.in_(("concept_phase1", "concept_phase2")))


def _transition(
    db: Session,
    session: LearningSession,
    stage: str,
    prerequisite_id: str | None,
    is_correct: bool,
    misconception: str | None,
) -> tuple[str, bool, bool]:
    previous = (
        _scope_attempts(db, session, stage, prerequisite_id)
        .order_by(LearningChoiceAttempt.created_at.desc())
        .first()
    )
    if is_correct:
        return ("resolution" if previous and not previous.is_correct else "correct"), False, False
    previous_type = previous.misconception_type if previous else None
    persistence = bool(previous_type and previous_type == misconception and misconception != "unknown")
    prior_resolved = (
        _scope_attempts(db, session, stage, prerequisite_id)
        .filter(LearningChoiceAttempt.is_correct.is_(True))
        .first()
        is not None
    )
    recurrence = bool(prior_resolved and misconception not in {None, "unknown"})
    if persistence:
        return "persistence", True, False
    if recurrence:
        return "recurrence", False, True
    if previous_type and misconception and previous_type != misconception:
        return f"{previous_type}_to_{misconception}", False, False
    return ("knowledge_gap" if misconception == "unknown" else "initial"), False, False


def _update_target_state(
    db: Session,
    session: LearningSession,
    option: LearningQuestionOption,
    attempt: LearningChoiceAttempt,
) -> None:
    if attempt.stage not in {"concept_phase1", "concept_phase2"}:
        return
    state = db.query(LearnerState).filter_by(participant_id=session.participant_id, term_id=session.term_id).one_or_none()
    if not state:
        return
    state.current_status = "resolved" if option.is_correct else ("unknown" if option.misconception_type == "unknown" else "misconception")
    state.primary_misconception = None if option.is_correct else option.misconception_type
    state.resolution_stage = "confirmed_in_learning" if option.is_correct and attempt.stage == "concept_phase2" else ("provisional" if option.is_correct else "none")
    state.updated_reason = attempt.transition_type


async def _feedback(
    db: Session,
    session: LearningSession,
    question: LearningQuestion,
    option: LearningQuestionOption,
    forced: bool,
) -> tuple[str, dict[str, Any] | None]:
    term = db.get(Term, session.term_id)
    definition = _definition_by_key(db, session, session.current_prerequisite_key)
    if option.is_correct or forced:
        result = await _ai_call(
            db,
            "generate_correct_answer_summary",
            {
                "participant_id": session.participant_id,
                "group_condition": session.group_condition,
                "target_term": {"slug": term.slug, "label": term.label},
                "focus_label": definition.label if definition else term.label,
                "question_body": question.body,
                "selected_option_body": option.body if option.is_correct else None,
                "rag_context": _learning_rag_context(term, definition.label if definition else ""),
            },
        )
        return result["summary"], result
    payload: dict[str, Any] = {
        "participant_id": session.participant_id,
        "group_condition": session.group_condition,
        "target_term": {"slug": term.slug, "label": term.label},
        "focus_label": definition.label if definition else term.label,
        "question_body": question.body,
        "selected_option_body": option.body,
        "rag_context": _learning_rag_context(term, option.body),
    }
    if session.group_condition == "proposed":
        participant = get_participant(db, session.participant_id)
        payload["diagnosis_context"] = _initial_test_context(db, participant, term)
        payload["retest_context"] = _latest_retest_context(db, participant, term)
        payload["learning_history"] = _history(db, session)
    result = await _ai_call(db, "explain_selected_distractor", payload)
    return result["feedback"], result


def _complete_prerequisite_slot(
    db: Session,
    session: LearningSession,
    forced: bool,
) -> LearningSessionPrerequisite:
    row = (
        db.query(LearningSessionPrerequisite)
        .filter_by(learning_session_id=session.id, prerequisite_key=session.current_prerequisite_key)
        .one()
    )
    row.completed_slot_count = min(2, row.completed_slot_count + 1)
    if forced:
        row.forced_slot_count += 1
    if row.completed_slot_count >= 2:
        row.status = "completed"
    return row


async def _advance_after_completed_slot(
    db: Session,
    session: LearningSession,
    stage: str,
    forced: bool,
) -> None:
    if stage == "prerequisite":
        row = _complete_prerequisite_slot(db, session, forced)
        if "slot1" in (session.current_slot_key or ""):
            session.current_slot_key = f"prerequisite:{session.current_prerequisite_key}:slot2"
            session.current_attempt_index = 1
            return
        prereqs = _session_prerequisite_rows(db, session)
        next_row = next((item for item in prereqs if item.display_order > row.display_order), None)
        if next_row:
            session.current_prerequisite_key = next_row.prerequisite_key
            session.current_slot_key = f"prerequisite:{next_row.prerequisite_key}:slot1"
            session.current_attempt_index = 1
            await _generate_material(db, session, "prerequisite", "initial")
            return
        session.current_stage = "concept_phase1"
        session.status = "concept_phase1"
        session.current_prerequisite_key = None
        session.current_slot_key = "phase1:cycle1:slot1"
        session.current_attempt_index = 1
        session.current_cycle_index = 1
        await _generate_material(db, session, "concept_phase1", "initial")
        return
    if stage == "concept_phase1":
        if "slot1" in (session.current_slot_key or ""):
            session.current_slot_key = f"phase1:cycle{session.current_cycle_index}:slot2"
            session.current_attempt_index = 1
            return
        session.current_stage = "completed"
        session.status = "completed"
        session.current_slot_key = None
        session.current_attempt_index = 1
        session.current_material_id = None
        session.completed_at = now()


async def _start_prerequisite_review(
    db: Session,
    session: LearningSession,
    linked_keys: list[str],
) -> None:
    definitions = _definitions(db, session)
    fallback = definitions[0].prerequisite_key
    review_key = next((key for key in linked_keys if _definition_by_key(db, session, key)), fallback)
    review_row = (
        db.query(LearningSessionPrerequisite)
        .filter_by(learning_session_id=session.id, prerequisite_key=review_key)
        .one()
    )
    review_row.review_count += 1
    slot_index = 1 if review_row.review_count % 2 else 2
    slot_key = f"prerequisite:{review_key}:slot{slot_index}"
    session.review_return_slot_key = session.current_slot_key
    session.review_prerequisite_key = review_key
    session.current_stage = "prerequisite_review"
    session.status = "prerequisite_review"
    session.current_prerequisite_key = review_key
    session.current_slot_key = slot_key
    session.current_attempt_index = _slot_attempt_count(db, session, slot_key) + 1
    await _generate_material(db, session, "prerequisite_review", "review")


async def _finish_review(db: Session, session: LearningSession) -> None:
    return_slot = session.review_return_slot_key
    session.current_stage = "concept_phase1"
    session.status = "concept_phase1"
    session.current_prerequisite_key = None
    session.current_slot_key = return_slot
    session.current_attempt_index = _slot_attempt_count(db, session, return_slot) + 1
    session.review_return_slot_key = None
    session.review_prerequisite_key = None
    await _generate_material(db, session, "concept_phase1", "after_prerequisite_review")


async def submit_fixed_learning_attempt(
    db: Session,
    session_id: str,
    stage: str,
    question_id: str,
    selected_option_id: str,
    idempotency_key: str | None,
    response_time_sec: float | None,
) -> dict[str, Any]:
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    existing = db.query(LearningChoiceAttempt).filter_by(idempotency_key=idempotency_key).one_or_none()
    if existing:
        session = db.get(LearningSession, existing.learning_session_id)
        return {
            "attempt_id": existing.id,
            "is_correct": existing.is_correct,
            "result_status": existing.result_status,
            "feedback": existing.feedback_text,
            "forced_answer_shown": existing.forced_answer_shown,
            "session": fixed_learning_session_state(db, session.id),
        }
    session = db.get(LearningSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="learning session not found")
    if session.status in {"completed", "technical_blocked"}:
        raise HTTPException(status_code=400, detail=f"session is {session.status}")
    expected_stage = session.current_stage
    if stage == "prerequisite" and expected_stage not in {"prerequisite", "prerequisite_review"}:
        raise HTTPException(status_code=409, detail="session is not in prerequisite stage")
    if stage != "prerequisite" and expected_stage != stage:
        raise HTTPException(status_code=409, detail=f"session is not in {stage}")
    question = _current_question(db, session)
    if question.id != question_id:
        raise HTTPException(status_code=409, detail="question is not current")
    option = db.get(LearningQuestionOption, selected_option_id)
    if not option or option.learning_question_id != question.id:
        raise HTTPException(status_code=400, detail="selected option does not belong to question")
    display = _display_order(db, session.participant_id, question)
    definition = _definition_by_key(db, session, session.current_prerequisite_key)
    actual_stage = session.current_stage or stage
    forced = not option.is_correct and (
        session.current_attempt_index >= MAX_SLOT_ATTEMPTS
        and actual_stage != "concept_phase2"
        or actual_stage == "concept_phase2"
        and session.group_condition == "proposed"
        and session.current_attempt_index >= MAX_PHASE2_ATTEMPTS
    )
    transition, persistence, recurrence = _transition(
        db,
        session,
        actual_stage,
        definition.id if definition else None,
        option.is_correct,
        option.misconception_type,
    )
    if actual_stage == "concept_phase2" and session.group_condition == "control":
        result_status = "completed"
    elif option.is_correct:
        result_status = "passed"
    elif forced:
        result_status = "forced_resolved" if actual_stage != "concept_phase2" else "completed"
    else:
        result_status = "retry"
    attempt = LearningChoiceAttempt(
        participant_id=session.participant_id,
        learning_session_id=session.id,
        target_term_id=session.term_id,
        prerequisite_definition_id=definition.id if definition else None,
        stage=actual_stage,
        slot_key=session.current_slot_key or "",
        question_id=question.id,
        selected_option_id=option.id,
        displayed_option_order=display.option_order,
        cycle_index=session.current_cycle_index,
        attempt_index=session.current_attempt_index,
        is_correct=option.is_correct,
        misconception_type=option.misconception_type,
        transition_type=transition,
        is_persistence=persistence,
        is_recurrence=recurrence,
        result_status=result_status,
        forced_answer_shown=forced,
        response_time_sec=response_time_sec,
        material_id=session.current_material_id,
        idempotency_key=idempotency_key,
    )
    db.add(attempt)
    db.flush()
    _update_target_state(db, session, option, attempt)
    feedback, _ = await _feedback(db, session, question, option, forced)
    attempt.feedback_text = feedback
    session.last_feedback = feedback

    correct_answer: dict[str, str] | None = None
    if forced:
        correct_option = next(item for item in _question_options(db, question.id) if item.is_correct)
        correct_answer = {"body": correct_option.body, "summary": feedback}

    if actual_stage == "prerequisite_review":
        await _finish_review(db, session)
    elif actual_stage == "prerequisite":
        if option.is_correct or forced:
            await _advance_after_completed_slot(db, session, "prerequisite", forced)
        else:
            session.current_attempt_index += 1
            await _generate_material(db, session, "prerequisite", "retry")
    elif actual_stage == "concept_phase1":
        if option.is_correct or forced:
            await _advance_after_completed_slot(db, session, "concept_phase1", forced)
        elif session.group_condition == "proposed":
            await _start_prerequisite_review(db, session, option.linked_prerequisite_keys or [])
        else:
            session.current_attempt_index += 1
            await _generate_material(db, session, "concept_phase1", "retry")
    elif actual_stage == "concept_phase2":
        if session.group_condition == "control" or option.is_correct or forced:
            session.status = "completed"
            session.current_stage = "completed"
            session.completed_at = now()
            session.phase2_forced_completion = forced
        else:
            session.current_cycle_index += 1
            session.current_stage = "concept_phase1"
            session.status = "concept_phase1"
            session.current_slot_key = f"phase1:cycle{session.current_cycle_index}:slot1"
            session.current_attempt_index = 1
            await _generate_material(db, session, "concept_phase1", "after_phase2_failure")
    if session.status not in {"completed", "technical_blocked"}:
        await _ensure_question_available(db, session)
    db.commit()
    return {
        "attempt_id": attempt.id,
        "is_correct": option.is_correct,
        "result_status": result_status,
        "feedback": feedback,
        "forced_answer_shown": forced,
        "correct_answer": correct_answer,
        "session": fixed_learning_session_state(db, session.id),
    }


async def retry_fixed_learning_material(db: Session, session_id: str) -> dict[str, Any]:
    session = db.get(LearningSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="learning session not found")
    if session.status != "technical_blocked":
        raise HTTPException(status_code=409, detail="session is not technically blocked")
    stage = session.current_stage or "prerequisite"
    await _generate_material(db, session, stage, "technical_retry")
    await _ensure_question_available(db, session)
    return fixed_learning_session_state(db, session.id)
