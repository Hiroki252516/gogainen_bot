from __future__ import annotations

import asyncio
import csv
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ai.codex_app_server_backend import CodexAppServerError
from app.ai.backend import strategy_for
from app.ai.factory import get_ai_backend
from app.ai.interaction_history import SHARED_QUESTION_ROUTE_VERSION, interaction_history_audit, project_model_payload
from app.ai.mandatory_elements import (
    MANDATORY_MISCONCEPTION_TYPES,
    expected_mandatory_type,
    mandatory_element_requirements,
    validate_mandatory_elements,
)
from app.ai.misconception_taxonomy import TAXONOMY_VERSION, taxonomy_for_prompt
from app.ai.material_structure import validate_material_structure
from app.ai.teaching_contract import (
    MATERIAL_MAX_CHARACTERS,
    MATERIAL_MIN_CHARACTERS,
    MATERIAL_TARGET_CHARACTERS,
    PROMPT_CONTRACT_VERSION,
    validate_tutoring_material_safety,
    validate_teaching_contract,
    validate_tutoring_material_length,
)
from app.core.config import get_settings
from app.core.experiment_spec import (
    CURRENT_EXPERIMENT_SPEC_VERSION,
    CURRENT_PROTOCOL_ID,
    MAX_POST_PRETEST_TESTS,
    assert_current_experiment,
    can_resume,
)
from app.services.research_protocol import SURVEY_VERSION, validate_survey_for_participant
from app.services.hypothesis_metrics import METRICS_VERSION, participant_metrics, current_metrics, group_metrics, write_metrics_csv
from app.core.runtime_config import (
    STUDY_MODEL,
    STUDY_REASONING_EFFORT,
    current_ai_runtime_settings,
)
from app.core.question_sets import STANDARD, ASSESSMENT_BANK_VERSIONS, HISTORICAL_ASSESSMENT_BANK_VERSIONS, LEARNING_CONTENT_VERSIONS, assessment_construct_key, question_set_mode, explanation_context
from app.services.question_sets import current_question_set_mode
from app.services.learning_glossary import glossary_snapshot, public_glossary
from app.db.session import SessionLocal
from app.rag.retriever import retrieve_rag_context
from app.seed.content_loader import (
    ASSESSMENT_VARIANT_COUNTS,
    LEARNING_SESSION_VARIANT_COUNT,
    content_term,
    learning_question_spec,
    load_content,
    teaching_target_for_option,
)
from app.models import (
    AICallLog,
    AuditEvent,
    Attempt,
    EvaluationSummary,
    ExportJob,
    IdempotencyRecord,
    LearnerState,
    Participant,
    ParticipantSurvey,
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
from app.services.idempotency import idempotency_error, run_idempotent
from app.services.legacy_logs import legacy_fields, legacy_selected_option_body, legacy_turn_answer_rows
from app.services.interaction_history import build_interaction_history
from app.services.option_order import (
    assessment_bank_index,
    current_option_order_mode,
    learning_bank_index,
    present_options,
)
from app.services.tutor_prefetch import PrefetchHandle


PRETEST_TERM_ORDER = {
    term["slug"]: index for index, term in enumerate(load_content()["terms"])
}
PRETEST_TERM_SLUGS = set(PRETEST_TERM_ORDER)
LEARNING_STAGE_LABELS = {
    "enrichment": "豊富化",
    "conceptual_change": "概念変化",
    "final_feedback": "教材フィードバック",
}
TEST_PHASES = {"pretest", "retest", "final_test"}
ATTEMPT_PHASES = TEST_PHASES
FINAL_TEST_NOT_AVAILABLE_DETAIL = "この参加者は最終テスト対象ではありません。"
RETEST_ALLOWED_STEPS = {"learning_targets", "retest"}
LEARNING_ALLOWED_STEPS = {"learning_targets"}
RETEST_NOT_AVAILABLE_DETAIL = "この参加者は再テスト対象ではありません。"
LEARNING_NOT_AVAILABLE_DETAIL = "この参加者は学習セッション対象ではありません。"
EXPERIMENT_FINISHED_DETAIL = "この実験は終了しています。"
# Both validation paths include the initial generation plus up to two retries.
MANDATORY_ELEMENT_MAX_ATTEMPTS = 3
MATERIAL_LENGTH_MAX_ATTEMPTS = 3
PREFETCH_STATES = {"pending", "generating", "ready", "consumed", "failed", "discarded"}
PREFETCH_WAITING_STATES = {"pending", "generating", "ready"}


@dataclass
class TutorTurnGenerationPlan:
    session_id: str
    participant_id: str
    group_condition: str
    turn_index: int
    learner_prompt: str
    practice_question: dict[str, Any]
    position: dict[str, Any]
    payload: dict[str, Any]
    forbidden_material: list[str]
    generation_origin: str
    prefetch_audit: dict[str, Any] | None
    learning_content_version: int


def _commit(db: Session) -> None:
    """Commit normally, or flush when an idempotent route owns the transaction."""
    if db.info.get("defer_commits"):
        db.flush()
    else:
        db.commit()


def _component_terms(term_slug: str, term_label: str) -> list[str]:
    try:
        return list(content_term(term_slug).get("component_terms") or [term_label])
    except StopIteration:
        return [term_label]


def _learning_question_spec(
    term_slug: str,
    learning_stage: str,
    variant_index: int = 1,
    mode: str = STANDARD,
    *, content_version: int | None = None,
) -> dict[str, Any]:
    try:
        return learning_question_spec(term_slug, learning_stage, variant_index, mode, content_version=content_version)
    except (KeyError, StopIteration, ValueError) as exc:
        raise HTTPException(status_code=400, detail="fixed learning question not found") from exc


def _public_learning_options(
    spec: dict[str, Any],
    participant: Participant,
    term_slug: str,
    learning_stage: str,
    variant_index: int,
) -> list[dict[str, Any]]:
    return present_options(
        spec["options"],
        mode=participant.option_order_mode,
        bank="learning",
        item_index=learning_bank_index(term_slug, learning_stage, variant_index),
    )


def _selection_constraints(question_type: str | None, option_count: int) -> dict[str, Any]:
    if question_type and "multi_select" in question_type:
        return {"selection_mode": "multiple", "min_selections": 3, "max_selections": 3}
    raise HTTPException(status_code=400, detail="unsupported question type")


def _learning_option_meta(spec: dict[str, Any], option_id: str | None) -> dict[str, Any] | None:
    if not option_id:
        return None
    return next((option for option in spec["options"] if option["option_id"] == option_id), None)


def _selected_learning_options(
    spec: dict[str, Any],
    selected_option_ids: list[str] | None,
    displayed_options: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    ids = selected_option_ids or []
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=400, detail="duplicate selected options")
    if displayed_options:
        displayed_by_id = {
            str(option.get("option_id")): option
            for option in displayed_options
            if isinstance(option, dict) and option.get("option_id")
        }
        spec_by_body = {str(option["body"]): option for option in spec["options"]}
        selected_displays = [displayed_by_id.get(str(option_id)) for option_id in ids]
        if any(option is None for option in selected_displays):
            raise HTTPException(status_code=400, detail="invalid selected options")
        options = [spec_by_body.get(str(option["body"])) for option in selected_displays]
    else:
        options = [_learning_option_meta(spec, option_id) for option_id in ids]
    if any(option is None for option in options):
        raise HTTPException(status_code=400, detail="invalid selected options")
    return options


def _selected_labels(options: list[dict[str, Any]]) -> str:
    return " / ".join(option["label"] for option in options)


def _option_misconception(option: Any) -> str | None:
    return option.misconception_type if hasattr(option, "misconception_type") else option.get("misconception_type")


def _validate_multi_select_options(options: list[Any], selected_count: int) -> None:
    unknown_count = sum(_option_misconception(option) == "unknown" for option in options)
    if unknown_count == 1 and selected_count == 1:
        return
    if unknown_count:
        raise HTTPException(status_code=400, detail="unknown option cannot be combined with other options")
    if selected_count != 3 or len(options) != selected_count:
        raise HTTPException(status_code=400, detail="select exactly three options or only the unknown option")


def _option_is_correct(option: Any) -> bool:
    return bool(option.is_correct if hasattr(option, "is_correct") else option.get("is_correct"))


def _classify_selected_options(
    options: list[Any],
) -> tuple[bool, str | None, str]:
    misconceptions = [_option_misconception(option) for option in options]
    if "M3" in misconceptions:
        return False, "M3", "misconception"
    if "M1" in misconceptions:
        return False, "M1", "misconception"
    options_are_correct = len(options) == 3 and all(_option_is_correct(option) for option in options)
    if options_are_correct:
        return True, None, "stable_correct"
    return False, "unknown", "unknown"


def _fixed_feedback_for_options(options: list[dict[str, Any]], spec: dict[str, Any]) -> dict[str, Any]:
    if not options:
        is_correct, mtype, status = False, "unknown", "unknown"
        selected_label_text = "未選択"
    else:
        is_correct, mtype, status = _classify_selected_options(options)
        selected_label_text = _selected_labels(options)
    return {
        "feedback": "選択内容は十分です。次の確認へ進みます。" if is_correct else "選択内容はまだ不十分です。教材を確認して、もう一度選び直してください。",
        "is_sufficient": is_correct,
        "next_action": "move_next" if is_correct else "continue",
        "learning_misconception_type": mtype,
        "learning_misconception_confidence": 0.95,
        "learning_misconception_reason": "固定3選択式問題で正解選択肢だけを選びました。" if is_correct else f"固定3選択式問題で{mtype}相当として判定しました。",
        "state_update_reason": "fixed_multi_select_correct" if is_correct else f"fixed_multi_select_{status}",
        "selected_option_body": selected_label_text,
    }


def _practice_question_text(practice_question: dict[str, Any] | None) -> str:
    if not practice_question:
        return ""
    if practice_question.get("body"):
        return practice_question["body"]
    return ""


def _misconception_teaching_guidance(misconception_type: str | None) -> str:
    return {
        "M1": "単一の誤った命題、正しい考え、反例、誤りの理由を教材のセクション本文へ含める。専用見出しや記述順序は要求しない。",
        "M3": "対象概念の誤カテゴリー、正カテゴリー、境界基準、近いカテゴリーとの比較を教材のセクション本文へ含める。専用見出しや記述順序は要求しない。",
        "unknown": "誤概念を推測せず、対象用語の意味や仕組みと、別事例への適用確認を教材本文に含める。",
    }.get(misconception_type, "現在の構成用語の定義、役割、判断基準を短く整理する。")


def _material_length_retry(length_validation: dict[str, Any], attempt: int) -> dict[str, Any]:
    return {
        "attempt": attempt,
        "target_character_count": MATERIAL_TARGET_CHARACTERS,
        "min_character_count": MATERIAL_MIN_CHARACTERS,
        "max_character_count": MATERIAL_MAX_CHARACTERS,
        "actual_character_count": length_validation.get("character_count"),
    }


async def _generate_validated_tutoring_turn(
    db: Session,
    payload: dict[str, Any],
    *,
    forbidden_strings: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    group = payload.get("group_condition", "proposed")
    expected_type = expected_mandatory_type({**payload, "group_condition": group}) if group == "proposed" else None
    selected_strategy = strategy_for(expected_type, None, group)
    term_label = (payload.get("term") or {}).get("label")
    retry_limit = max(MANDATORY_ELEMENT_MAX_ATTEMPTS, MATERIAL_LENGTH_MAX_ATTEMPTS)
    request_payload = {**payload, "generation_attempt": 1}
    validation: dict[str, Any] = {}
    for attempt in range(1, retry_limit + 1):
        result = await _ai_call(db, "generate_tutoring_turn", request_payload)
        mandatory = validate_mandatory_elements(result, expected_type, term_label)
        contract = validate_teaching_contract(result, expected_type, payload, term_label)
        safety = validate_tutoring_material_safety(result, forbidden_strings)
        length = validate_tutoring_material_length(result)
        structure = validate_material_structure(result, term_label)
        strategy_valid = result.get("teaching_strategy") == selected_strategy
        retry_missing = list(dict.fromkeys([
            *mandatory.get("missing", []), *contract.get("missing", []),
            *safety.get("missing", []), *structure["missing"],
        ]))
        if not strategy_valid:
            retry_missing.append("teaching_strategy.mismatch")
        validation = {
            **mandatory,
            "valid": mandatory["valid"] and contract["valid"] and safety["valid"] and length["valid"] and structure["valid"] and strategy_valid,
            "missing": [*retry_missing, *length.get("missing", [])],
            "teaching_contract": contract,
            "material_safety": safety,
            "material_length": length,
            "material_structure": structure,
            "teaching_strategy": {"expected": selected_strategy, "actual": result.get("teaching_strategy"), "valid": strategy_valid},
            "attempt": attempt,
        }
        _attach_generation_validation(db, request_payload, validation)
        if validation["valid"]:
            return result, {**validation, "attempts": attempt}
        if attempt < retry_limit:
            request_payload = {**payload, "generation_attempt": attempt + 1}
            if not length["valid"]:
                request_payload["material_length_retry"] = _material_length_retry(length, attempt + 1)
            if retry_missing:
                request_payload["mandatory_element_retry"] = {"attempt": attempt + 1, "missing": retry_missing}
    raise HTTPException(status_code=503, detail={
        "error_code": "teaching_contract_invalid",
        "message": "教材の生成契約を満たす教材を生成できませんでした。",
        "missing": validation.get("missing", []),
    })


def _attach_generation_validation(
    db: Session | None,
    request_payload: dict[str, Any],
    validation: dict[str, Any],
) -> None:
    """Attach server-side validation to the matching existing AI-call log."""
    if db is None:
        return

    participant_id = request_payload.get("participant_id")
    term_slug = (request_payload.get("term") or {}).get("slug")
    attempt = request_payload.get("generation_attempt", 1)
    if not participant_id or not term_slug:
        raise RuntimeError(
            "tutoring generation validation requires participant and term identifiers"
        )

    def matches(log: AICallLog) -> bool:
        logged = log.request_payload or {}
        return (
            log.purpose == "generate_tutoring_turn"
            and logged.get("participant_id") == participant_id
            and (logged.get("term") or {}).get("slug") == term_slug
            and logged.get("generation_attempt", 1) == attempt
        )

    deferred_logs = db.info.get("deferred_ai_logs", [])
    log = next((candidate for candidate in reversed(deferred_logs) if matches(candidate)), None)
    if log is None:
        candidates = (
            db.query(AICallLog)
            .filter_by(purpose="generate_tutoring_turn")
            .order_by(AICallLog.created_at.desc(), AICallLog.id.desc())
            .limit(50)
            .all()
        )
        log = next((candidate for candidate in candidates if matches(candidate)), None)
    if log is None:
        raise RuntimeError("tutoring generation validation has no matching AI-call log")

    log.response_payload = {
        **(log.response_payload or {}),
        "generation_validation": validation,
    }
    if not db.info.get("defer_commits"):
        db.commit()


def _practice_meta(turn: TutorTurn | None) -> dict[str, Any]:
    if not turn or not isinstance(turn.practice_question_json, dict):
        return {}
    return turn.practice_question_json.get("stage_meta") or {}


def _learning_stage_for_misconception(misconception_type: str | None, status: str | None = None) -> str:
    return "enrichment" if misconception_type == "unknown" or status == "unknown" else "conceptual_change"


def _learning_stage_label_for_state(state: LearnerState) -> str:
    if state.current_status in {"misconception", "unknown"}:
        return LEARNING_STAGE_LABELS[_learning_stage_for_misconception(state.primary_misconception, state.current_status)]
    return "概念理解を確認"


def _learning_position(db: Session, session: TutorSession, term: Term, participant: Participant) -> dict[str, Any]:
    state = db.query(LearnerState).filter_by(participant_id=session.participant_id, term_id=session.term_id).one_or_none()
    turns = (
        db.query(TutorTurn)
        .filter_by(tutor_session_id=session.id)
        .order_by(TutorTurn.turn_index)
        .all()
    )
    stage = _learning_stage_for_misconception(state.primary_misconception if state else None, state.current_status if state else None)
    for turn in turns:
        if not turn.learner_response:
            continue
        grading = turn.grading_json or {}
        if grading.get("is_sufficient"):
            stage = "final_feedback"
        else:
            stage = _learning_stage_for_misconception(grading.get("learning_misconception_type"), grading.get("diagnosed_status"))
    return {
        "learning_stage": stage,
        "learning_stage_label": LEARNING_STAGE_LABELS[stage],
        "component_terms": _component_terms(term.slug, term.label),
    }


def _actual_tutoring_input(payload: dict[str, Any], group_condition: str) -> dict[str, Any]:
    return project_model_payload(payload, proposed=group_condition == "proposed")


def _merge_stage_meta(practice_question: dict[str, Any], position: dict[str, Any]) -> dict[str, Any]:
    practice_question = dict(practice_question or {})
    practice_question["stage_meta"] = {
        "learning_stage": position["learning_stage"],
        "learning_stage_label": position["learning_stage_label"],
        "component_terms": position.get("component_terms") or [],
    }
    return practice_question


def session_misconception_history(db: Session, session_id: str) -> list[dict[str, Any]]:
    session = db.get(TutorSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="tutor session not found")
    assert_current_experiment(get_participant(db, session.participant_id))
    turns = db.query(TutorTurn).filter_by(tutor_session_id=session_id).order_by(TutorTurn.turn_index).all()
    history = []
    for turn in turns:
        grading = turn.grading_json or {}
        if "learning_misconception_type" not in grading:
            continue
        stage = grading.get("learning_stage") or "conceptual_change"
        history.append({
            "turn_id": turn.id,
            "turn_index": turn.turn_index,
            "learning_stage": stage,
            "label": LEARNING_STAGE_LABELS.get(stage, "概念変化"),
            "misconception_type": grading.get("learning_misconception_type"),
            "confidence": grading.get("learning_misconception_confidence"),
            "reason": grading.get("learning_misconception_reason"),
            "is_sufficient": grading.get("is_sufficient"),
        })
    return history


def _rag_query(*parts: str | None) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


def _rag_context(term_slug: str, *parts: str | None) -> dict[str, Any]:
    term_config = content_term(term_slug)
    return retrieve_rag_context(
        _rag_query(*parts),
        top_k=3,
        allowed_sections=term_config.get("rag_sections") or [],
        topic_slug=term_slug,
    )


def _pretest_teaching_targets(term_slug: str, options: list[QuestionOption], mode: str = STANDARD) -> list[dict[str, Any]]:
    """Build proposal-only targets from selected pretest distractors and seed metadata."""
    targets: list[dict[str, Any]] = []
    for option in sorted(options, key=lambda item: item.option_label):
        if option.is_correct or option.misconception_type not in {"M1", "M3"}:
            continue
        metadata = teaching_target_for_option(term_slug, option.option_label, mode)
        if not metadata:
            continue
        target = {
            "claim_id": f"{term_slug}:pretest:{option.option_label}",
            "term_slug": term_slug,
            "option_label": option.option_label,
            "observed_claim": option.body,
            "corrected_claim": metadata["corrected_claim"],
            "mechanism_explanation": metadata["mechanism_explanation"],
            "contrast_example": metadata["contrast_example"],
            "misconception_type": option.misconception_type,
            "evidence_source": "pretest_selected_option",
            "interpretation": "observed_choice_not_confirmed_belief",
        }
        for field in ("wrong_category", "correct_category", "boundary_criterion"):
            if metadata.get(field):
                target[field] = metadata[field]
        targets.append(target)
    return targets


def _primary_pretest_target(targets: list[dict[str, Any]], misconception_type: str | None) -> dict[str, Any] | None:
    """Select only an observed target for the active M1/M3 teaching strategy."""
    if misconception_type not in {"M1", "M3"}:
        return None
    return next(
        (target for target in targets if target.get("misconception_type") == misconception_type),
        None,
    )


def get_participant(db: Session, participant_id: str, *, for_update: bool = False) -> Participant:
    query = db.query(Participant).filter_by(id=participant_id)
    if for_update:
        query = query.with_for_update()
    participant = query.one_or_none()
    if not participant:
        raise HTTPException(status_code=404, detail="participant not found")
    return participant


def participant_give_up_counts(db: Session, participant_ids: list[str]) -> dict[tuple[str, str], int]:
    if not participant_ids:
        return {}
    rows = (
        db.query(AuditEvent.entity_id, AuditEvent.action, func.count(AuditEvent.id))
        .filter(
            AuditEvent.entity_type == "participant",
            AuditEvent.action.in_(["give_up_learning", "give_up_experiment"]),
            AuditEvent.entity_id.in_(participant_ids),
        )
        .group_by(AuditEvent.entity_id, AuditEvent.action)
        .all()
    )
    return {(entity_id, action): int(count) for entity_id, action, count in rows}


def _assert_participant_active(participant: Participant) -> None:
    assert_current_experiment(participant)
    if participant.current_step == "finish" or participant.completed_at is not None:
        raise HTTPException(status_code=409, detail=EXPERIMENT_FINISHED_DETAIL)


def _assert_learning_available(participant: Participant) -> None:
    _assert_participant_active(participant)
    if participant.current_step not in LEARNING_ALLOWED_STEPS:
        raise HTTPException(status_code=409, detail=LEARNING_NOT_AVAILABLE_DETAIL)


def _assert_learning_give_up_available(participant: Participant) -> None:
    _assert_participant_active(participant)
    if participant.current_step != "learning_targets":
        raise HTTPException(status_code=409, detail=LEARNING_NOT_AVAILABLE_DETAIL)


def _assert_retest_available(participant: Participant) -> None:
    _assert_participant_active(participant)
    if participant.current_step not in RETEST_ALLOWED_STEPS:
        raise HTTPException(status_code=409, detail=RETEST_NOT_AVAILABLE_DETAIL)


def _assert_phase_available(participant: Participant, phase: str) -> None:
    if phase not in ATTEMPT_PHASES:
        raise HTTPException(status_code=400, detail="unsupported attempt phase")
    if phase == "pretest":
        if participant.current_step != "pretest":
            raise HTTPException(status_code=409, detail="この参加者はテスト対象ではありません。")
    elif phase == "retest":
        _assert_retest_available(participant)
    elif phase == "final_test":
        if participant.current_step != "final_test":
            raise HTTPException(status_code=409, detail=FINAL_TEST_NOT_AVAILABLE_DETAIL)


def _close_open_tutor_sessions(db: Session, participant_id: str) -> int:
    open_sessions = db.query(TutorSession).filter_by(participant_id=participant_id, ended_at=None).all()
    ended_at = now()
    for session in open_sessions:
        if _prefetch_state(session) in PREFETCH_WAITING_STATES | {"failed"}:
            session.prefetch_state = "discarded"
            session.prefetch_discarded_at = ended_at
            session.prefetch_error_code = "participant_session_closed"
            _update_prefetch_ai_logs(db, session.id, disposition="discarded", error_code="participant_session_closed")
        session.ended_at = ended_at
    return len(open_sessions)


def give_up_learning(db: Session, participant_id: str) -> dict[str, Any]:
    """Skip the current learning session and make the next step the retest."""
    participant = get_participant(db, participant_id, for_update=True)
    _assert_learning_give_up_available(participant)
    before_step = participant.current_step
    closed_sessions = _close_open_tutor_sessions(db, participant.id)
    participant.current_step = "retest"
    db.add(
        AuditEvent(
            actor="participant",
            action="give_up_learning",
            entity_type="participant",
            entity_id=participant.id,
            before_json={"current_step": before_step},
            after_json={"current_step": participant.current_step, "closed_tutor_sessions": closed_sessions},
        )
    )
    _commit(db)
    return {
        "status": "completed",
        "action": "give_up_learning",
        "next_step": participant.current_step,
        "next_url": _next_url(participant.current_step),
        "closed_tutor_sessions": closed_sessions,
    }


def give_up_experiment(db: Session, participant_id: str) -> dict[str, Any]:
    """End the participant's experiment and route test users to the survey."""
    participant = get_participant(db, participant_id, for_update=True)
    assert_current_experiment(participant)
    before_step = participant.current_step
    before_completed_at = participant.completed_at.isoformat() if participant.completed_at else None
    already_finished = participant.current_step == "finish" and participant.completed_at is not None

    if already_finished:
        closed_sessions = _close_open_tutor_sessions(db, participant.id)
        if closed_sessions:
            _commit(db)
        return {
            "status": "completed",
            "action": "give_up_experiment",
            "next_step": participant.current_step,
            "next_url": _next_url(participant.current_step),
            "closed_tutor_sessions": closed_sessions,
        }

    if before_step == "survey":
        if participant.completion_reason == "give_up":
            return {
                "status": "completed",
                "action": "give_up_experiment",
                "next_step": participant.current_step,
                "next_url": _next_url(participant.current_step),
                "closed_tutor_sessions": 0,
            }
        raise HTTPException(status_code=409, detail="この参加者はアンケート対象です。")

    closed_sessions = _close_open_tutor_sessions(db, participant.id)
    participant.current_step = "survey" if before_step in {"retest", "final_test"} else "finish"
    participant.completed_at = participant.completed_at or now()
    participant.completion_reason = "give_up"
    db.add(
        AuditEvent(
            actor="participant",
            action="give_up_experiment",
            entity_type="participant",
            entity_id=participant.id,
            before_json={"current_step": before_step, "completed_at": before_completed_at},
            after_json={
                "current_step": participant.current_step,
                "completed_at": participant.completed_at.isoformat(),
                "completion_reason": participant.completion_reason,
                "closed_tutor_sessions": closed_sessions,
            },
        )
    )
    _commit(db)
    return {
        "status": "completed",
        "action": "give_up_experiment",
        "next_step": participant.current_step,
        "next_url": _next_url(participant.current_step),
        "closed_tutor_sessions": closed_sessions,
    }


def next_display_code(db: Session) -> str:
    display_codes = db.query(Participant.display_code).all()
    max_number = 0
    for (display_code,) in display_codes:
        match = re.fullmatch(r"P(\d+)", display_code or "")
        if match:
            max_number = max(max_number, int(match.group(1)))
    return f"P{max_number + 1:03d}"


def create_participant(db: Session, assignment_code: str | None, consent_checked: bool) -> Participant:
    from app.services.identity_mapping import CONSENT_DOCUMENT_VERSION
    if not consent_checked:
        raise HTTPException(status_code=400, detail="同意書への同意が必要です。")
    normalized_code = (assignment_code or "").strip().upper()
    group_condition_by_code = {"A": "proposed", "B": "control"}
    group_condition = group_condition_by_code.get(normalized_code)
    if group_condition is None:
        raise HTTPException(status_code=400, detail="管理者から伝えられた参加コード（AまたはB）が必要です。")
    mode = current_question_set_mode(db)
    participant = Participant(
        display_code=next_display_code(db),
        group_condition=group_condition,
        assignment_method="admin_code",
        consent_checked=consent_checked,
        consent_document_version=CONSENT_DOCUMENT_VERSION,
        consented_at=now(),
        current_step="pretest",
        learning_content_version=LEARNING_CONTENT_VERSIONS[mode],
        question_set_mode=mode,
        experiment_spec_version=CURRENT_EXPERIMENT_SPEC_VERSION,
        protocol_id=CURRENT_PROTOCOL_ID,
        option_order_mode=current_option_order_mode(db),
        retest_cycles_completed=0,
        started_at=now(),
    )
    db.add(participant)
    _commit(db)
    db.refresh(participant)
    return participant


def submit_survey(db: Session, participant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Save the versioned questionnaire without reusing legacy five-point values."""
    participant = get_participant(db, participant_id, for_update=True)
    assert_current_experiment(participant)
    discard_unconsumed_prefetches(db, participant.id, reason="experiment_finished")
    existing = (
        db.query(ParticipantSurvey)
        .filter_by(participant_id=participant.id, phase="posttest")
        .order_by(ParticipantSurvey.created_at.desc(), ParticipantSurvey.id.desc())
        .first()
    )
    if participant.current_step == "finish":
        if participant.completion_reason in {"completed", "give_up"} and existing:
            return {
                "status": "completed",
                "survey_id": existing.id,
                "next_step": "finish",
                "next_url": _next_url("finish"),
            }
        raise HTTPException(status_code=409, detail=EXPERIMENT_FINISHED_DETAIL)
    if participant.current_step != "survey":
        raise HTTPException(status_code=409, detail="この参加者はアンケート対象ではありません。")

    before_step = participant.current_step
    if existing is None:
        responses = validate_survey_for_participant(db, participant, payload)
        existing = ParticipantSurvey(
            participant_id=participant.id,
            phase="posttest",
            survey_version=SURVEY_VERSION,
            responses_json={k: v for k, v in responses.items() if k != "free_comment"},
            free_comment=responses["free_comment"],
        )
        db.add(existing)
        db.flush()

    participant.current_step = "finish"
    participant.completed_at = participant.completed_at or now()
    if participant.completion_reason != "give_up":
        participant.completion_reason = "completed"
    db.add(
        AuditEvent(
            actor="participant",
            action="submit_survey",
            entity_type="participant",
            entity_id=participant.id,
            before_json={"current_step": before_step},
            after_json={
                "current_step": participant.current_step,
                "completion_reason": participant.completion_reason,
                "survey_id": existing.id,
            },
        )
    )
    _commit(db)
    db.refresh(existing)
    return {
        "status": "completed",
        "survey_id": existing.id,
        "next_step": participant.current_step,
        "next_url": _next_url(participant.current_step),
    }


def delete_participant(db: Session, participant_id: str) -> dict[str, Any]:
    participant = get_participant(db, participant_id, for_update=True)
    assert_current_experiment(participant)
    session_ids = [session.id for session in db.query(TutorSession).filter_by(participant_id=participant.id).all()]
    registration_keys = [row.idempotency_key for row in db.query(IdempotencyRecord).filter_by(
        participant_id=participant.id, scope="participant:create").all()]
    deleted_counts: dict[str, int] = {}

    def delete_by_participant(model: Any) -> None:
        deleted_counts[model.__tablename__] = db.query(model).filter_by(participant_id=participant.id).delete(synchronize_session=False)

    try:
        delete_by_participant(ParticipantSurvey)
        delete_by_participant(TermAssignment)
        delete_by_participant(QuestionDisplayOrder)
        delete_by_participant(RecurrenceEvent)
        if session_ids:
            deleted_counts["tutor_turns"] = db.query(TutorTurn).filter(TutorTurn.tutor_session_id.in_(session_ids)).delete(synchronize_session=False)
        else:
            deleted_counts["tutor_turns"] = 0
        delete_by_participant(TutorSession)
        delete_by_participant(LearnerState)
        delete_by_participant(EvaluationSummary)
        delete_by_participant(Attempt)
        delete_by_participant(IdempotencyRecord)

        ai_logs = db.query(AICallLog).all()
        participant_ai_logs = [log for log in ai_logs if (log.request_payload or {}).get("participant_id") == participant.id]
        for log in participant_ai_logs:
            db.delete(log)
        deleted_counts["ai_call_logs"] = len(participant_ai_logs)

        audit = AuditEvent(
            actor="admin_ui",
            action="delete_participant",
            entity_type="participant",
            entity_id=participant.id,
            before_json={
                "display_code": participant.display_code,
            "experiment_spec_version": participant.experiment_spec_version,
            "can_resume": can_resume(participant),
                "group_condition": participant.group_condition,
                "current_step": participant.current_step,
                "deleted_counts": deleted_counts,
                "registration_keys": registration_keys,
                "completion_reason": participant.completion_reason,
            },
            after_json={"deleted": True, "identity_mapping_cleanup": "pending"},
        )
        db.add(audit)
        db.delete(participant)
        _commit(db)
    except Exception:
        db.rollback()
        raise

    return {"participant_id": participant.id, "deleted": True, "deleted_counts": deleted_counts}


def _source_question_phase(phase: str) -> str:
    return phase


def _retest_variant_number(question: Question) -> int:
    match = re.fullmatch(r"retest_v(\d+)", question.variant_key or "")
    return int(match.group(1)) if match else 1


def post_pretest_tests_completed(db: Session, participant: Participant) -> int:
    # final_test is the first post-pretest measurement, not a learning cycle.
    scored_final = db.query(Attempt.id).filter(
        Attempt.participant_id == participant.id,
        Attempt.phase == "final_test",
        Attempt.is_correct.is_not(None),
    ).first() is not None
    return (participant.retest_cycles_completed or 0) + int(scored_final)


def post_pretest_test_progress(db: Session, participant: Participant) -> dict[str, int | None]:
    return {
        "post_pretest_tests_completed": post_pretest_tests_completed(db, participant) if can_resume(participant) else None,
        "post_pretest_test_limit": MAX_POST_PRETEST_TESTS if can_resume(participant) else None,
    }


def experiment_progress(db: Session, participant: Participant) -> dict[str, str | int] | None:
    if not can_resume(participant):
        return None

    if participant.current_step == "pretest":
        return {"stage_id": "pretest", "label": "事前テスト・採点中", "percent": 0}
    if participant.current_step in {"learning_targets", "retest", "final_test"}:
        completed = post_pretest_tests_completed(db, participant)
        if participant.current_step == "final_test" and completed != 0:
            return None
        if completed == 0:
            return {
                "stage_id": "post_pretest_1",
                "label": "再テスト1までの学習・再テスト1",
                "percent": 25,
            }
        if completed == 1:
            return {
                "stage_id": "post_pretest_2",
                "label": "再テスト2までの学習・再テスト2",
                "percent": 50,
            }
        return None
    if participant.current_step == "survey":
        return {"stage_id": "survey", "label": "アンケート", "percent": 75}
    if participant.current_step == "finish":
        return {"stage_id": "complete", "label": "実験手続き完了", "percent": 100}
    return None


def _expected_test_variant(db: Session, participant: Participant, phase: str) -> str:
    if phase == "pretest":
        return "pretest_v1"
    completed = post_pretest_tests_completed(db, participant)
    if completed >= MAX_POST_PRETEST_TESTS or (phase == "final_test" and completed != 0):
        raise HTTPException(status_code=409, detail="事前テスト後のテスト回数上限に達しています。")
    return f"retest_v{completed + 1}"


def _test_round_key_for_question(db: Session, participant: Participant, phase: str, question: Question) -> str | None:
    if phase == "pretest":
        return "test"
    if phase == "final_test":
        return "retest_1"
    if phase == "retest":
        return f"retest_{_retest_variant_number(question)}"
    return None


def _test_round_display_label(test_round: str | None) -> str | None:
    if test_round == "test":
        return "テスト"
    match = re.fullmatch(r"retest_(\d+)", test_round or "")
    if match:
        return f"再テスト{match.group(1)}"
    return None


def _question_query_for_phase(db: Session, participant: Participant, phase: str):
    source_phase = _source_question_phase(phase)
    query = db.query(Question).join(Term, Question.term_id == Term.id).filter(Question.phase == source_phase, Question.is_active.is_(True), Term.is_active.is_(True))
    query = query.filter(Question.construct_key.in_([
        assessment_construct_key(slug, phase, participant.question_set_mode) for slug in PRETEST_TERM_SLUGS
    ]))
    if phase == "pretest":
        query = query.filter(Term.slug.in_(PRETEST_TERM_SLUGS))
    if phase == "retest":
        query = query.filter(Term.slug.in_(PRETEST_TERM_SLUGS))
    return query.order_by(Term.display_order, Question.variant_key)


def _question_for_phase_variant(
    db: Session,
    participant: Participant,
    term_id: str,
    phase: str,
    candidates: list[Question],
) -> Question | None:
    if not candidates:
        return None
    expected_key = _expected_test_variant(db, participant, phase)
    selected = next((question for question in candidates if question.variant_key == expected_key), None)
    if selected is None:
        raise HTTPException(status_code=503, detail="今回のテスト問題が見つかりません。管理者に連絡してください。")
    return selected


def _displayed_options(db: Session, participant: Participant, question: Question) -> list[dict[str, Any]]:
    options = db.query(QuestionOption).filter(QuestionOption.question_id == question.id, QuestionOption.option_label.in_(list("ABCDEFGHIJ"))).order_by(QuestionOption.default_order).all()
    term = db.get(Term, question.term_id)
    if term is None:
        raise HTTPException(status_code=404, detail="question term not found")
    try:
        item_index = assessment_bank_index(term.slug, question.phase, question.variant_key)
    except (ValueError, IndexError):
        item_index = 0
    return present_options(
        options,
        mode=participant.option_order_mode,
        bank="assessment",
        item_index=item_index,
    )


def question_payloads(db: Session, participant_id: str, phase: str) -> list[dict[str, Any]]:
    participant = get_participant(db, participant_id)
    _assert_participant_active(participant)
    _assert_phase_available(participant, phase)
    all_questions = _question_query_for_phase(db, participant, phase).all()
    if {db.get(Term, question.term_id).slug for question in all_questions} != PRETEST_TERM_SLUGS:
        raise HTTPException(status_code=503, detail="今回のテスト問題が不足しています。管理者に連絡してください。")
    by_term: dict[str, list[Question]] = {}
    for question in all_questions:
        by_term.setdefault(question.term_id, []).append(question)
    questions = [
        selected
        for term_id, candidates in by_term.items()
        if (selected := _question_for_phase_variant(db, participant, term_id, phase, candidates)) is not None
    ]
    questions = sorted(
        questions,
        key=lambda question: PRETEST_TERM_ORDER.get(db.get(Term, question.term_id).slug, 99),
    )
    submitted_attempts_by_question: dict[str, Attempt] = {}
    submitted_attempts = (
        db.query(Attempt)
        .filter(
            Attempt.participant_id == participant.id,
            Attempt.phase == phase,
            Attempt.is_correct.is_(None),
        )
        .order_by(Attempt.created_at.asc(), Attempt.id.asc())
        .all()
    )
    for attempt in submitted_attempts:
        submitted_attempts_by_question.setdefault(attempt.question_id, attempt)
    out = []
    for question in questions:
        term = db.get(Term, question.term_id)
        public_options = _displayed_options(db, participant, question)
        test_round = _test_round_key_for_question(db, participant, phase, question)
        submitted_attempt = submitted_attempts_by_question.get(question.id)
        submitted_option_ids = [
            str(option_id)
            for option_id in (submitted_attempt.selected_option_ids or [])
            if option_id
        ] if submitted_attempt else []
        out.append(
            {
                "question_id": question.id,
                "term_slug": term.slug,
                "term_label": term.label,
                "body": _variant_body_for_round(db, participant.id, question, phase),
                "question_type": question.question_type,
                "options": public_options,
                "test_round": test_round,
                "test_round_label": _test_round_display_label(test_round),
                "answer_status": "submitted" if submitted_attempt else "unanswered",
                "submitted_answer": (
                    {
                        "selected_option_ids": submitted_option_ids,
                    }
                    if submitted_attempt
                    else None
                ),
                **_selection_constraints(question.question_type, len(public_options)),
            }
        )
    return out


def _variant_body_for_round(db: Session, participant_id: str, question: Question, phase: str) -> str:
    return question.body


def _naive_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _selected_ids_from_payload(payload: dict[str, Any]) -> list[str]:
    selected_option_ids = payload.get("selected_option_ids") or []
    return [str(option_id) for option_id in selected_option_ids if option_id]


def _attempt_answer_matches_payload(attempt: Attempt, payload: dict[str, Any]) -> bool:
    stored_ids = [str(option_id) for option_id in (attempt.selected_option_ids or []) if option_id]
    return (
        attempt.question_id == payload.get("question_id")
        and attempt.phase == (payload.get("phase") or attempt.phase)
        and stored_ids == _selected_ids_from_payload(payload)
    )


def submit_attempt(db: Session, payload: dict[str, Any], idempotency_key: str | None = None) -> Attempt:
    normalized_idempotency_key = (idempotency_key or "").strip() or None
    question = db.get(Question, payload["question_id"])
    if not question:
        raise HTTPException(status_code=404, detail="question not found")
    participant = (
        db.query(Participant)
        .filter_by(id=payload["participant_id"])
        .with_for_update()
        .one_or_none()
    )
    if not participant:
        raise HTTPException(status_code=404, detail="participant not found")
    phase = payload.get("phase") or question.phase
    _assert_participant_active(participant)
    if phase not in ATTEMPT_PHASES:
        raise HTTPException(status_code=400, detail="unsupported attempt phase")
    if question.phase != phase:
        raise HTTPException(status_code=400, detail="question phase does not match attempt phase")
    term = db.get(Term, question.term_id)
    if not question.is_active or not term or not term.is_active:
        raise HTTPException(status_code=404, detail="question not found")
    if question.construct_key != assessment_construct_key(term.slug, phase, participant.question_set_mode):
        raise HTTPException(status_code=409, detail="この問題は参加者の問題版と一致しません。")
    if phase in TEST_PHASES and term.slug not in PRETEST_TERM_SLUGS:
        raise HTTPException(status_code=400, detail="question is outside the active experiment terms")
    if normalized_idempotency_key:
        existing = (
            db.query(Attempt)
            .filter_by(participant_id=participant.id, idempotency_key=normalized_idempotency_key)
            .order_by(Attempt.created_at.asc(), Attempt.id.asc())
            .first()
        )
        if existing:
            if _attempt_answer_matches_payload(existing, payload):
                return existing
            raise idempotency_error(
                "idempotency_key_conflict",
                "同じIdempotency-Keyで別の回答が送信されました。元の回答を維持します。",
                attempt_id=existing.id,
            )
    _assert_phase_available(participant, phase)
    if question.variant_key != _expected_test_variant(db, participant, phase):
        raise HTTPException(status_code=409, detail="この問題は今回のテスト対象ではありません。")
    pending = (
        db.query(Attempt)
        .filter(
            Attempt.participant_id == participant.id,
            Attempt.question_id == question.id,
            Attempt.phase == phase,
            Attempt.is_correct.is_(None),
        )
        .order_by(Attempt.created_at.asc(), Attempt.id.asc())
        .first()
    )
    if pending:
        raise idempotency_error(
            "answer_already_submitted",
            "この問題はすでに回答済みです。回答は変更できません。",
            attempt_id=pending.id,
        )
    selected_option_ids = payload.get("selected_option_ids") or []
    selected_option_ids = [option_id for option_id in selected_option_ids if option_id]
    if len(selected_option_ids) != len(set(selected_option_ids)):
        raise HTTPException(status_code=400, detail="duplicate selected options")
    constraints = _selection_constraints(question.question_type, db.query(func.count(QuestionOption.id)).filter_by(question_id=question.id).scalar() or 0)
    selected_for_validation = db.query(QuestionOption).filter(QuestionOption.question_id == question.id, QuestionOption.id.in_(selected_option_ids or ["__none__"])).all()
    if len(selected_for_validation) != len(selected_option_ids):
        raise HTTPException(status_code=400, detail="invalid selected options")
    if constraints["selection_mode"] == "multiple":
        _validate_multi_select_options(selected_for_validation, len(selected_option_ids))
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
        test_round=_test_round_key_for_question(db, participant, phase, question),
        attempt_index=attempt_index,
        selected_option_ids=selected_option_ids or None,
        response_time_sec=payload.get("response_time_sec"),
        question_shown_at=_naive_datetime(payload.get("question_shown_at")),
        answered_at=_naive_datetime(payload.get("answered_at")),
        question_body_snapshot=_variant_body_for_round(db, participant.id, question, phase),
        option_order_snapshot=_displayed_options(db, participant, question),
        idempotency_key=normalized_idempotency_key,
    )
    db.add(attempt)
    _commit(db)
    db.refresh(attempt)
    return attempt


def _tutoring_output_metrics(result: dict[str, Any]) -> dict[str, int]:
    material = str(result.get("tutor_message") or "")
    character_count = len(material)
    return {
        "character_count": character_count,
        "target_character_count": MATERIAL_TARGET_CHARACTERS,
        "min_character_count": MATERIAL_MIN_CHARACTERS,
        "max_character_count": MATERIAL_MAX_CHARACTERS,
        "character_count_in_target_range": int(MATERIAL_MIN_CHARACTERS <= character_count <= MATERIAL_MAX_CHARACTERS),
        "paragraph_count": len([block for block in re.split(r"\n\s*\n", material.strip()) if block.strip()]),
        "bullet_count": len(re.findall(r"(?m)^\s*(?:[-*+] |\d+[.)] )", material)),
    }


def _effective_request_with_instruction_audit(
    request_audit: dict[str, Any],
    generation_audit: dict[str, Any] | None,
) -> dict[str, Any]:
    """Join provider-side prompt audit with the server-side route audit."""
    effective_request = dict(request_audit)
    if generation_audit:
        for key in (
            "instruction_route",
            "question_route_version",
            "interaction_history",
            "term_slug",
            "session_index",
            "turn_index",
            "problem_variant_key",
            "problem_variant_index",
            "actual_ai_input",
        ):
            if key in generation_audit:
                if key == "actual_ai_input" and effective_request.get(key) is not None:
                    continue
                effective_request[key] = generation_audit[key]
    return effective_request


async def _ai_call(db: Session, purpose: str, payload: dict[str, Any]) -> dict[str, Any]:
    model, reasoning_effort = current_ai_runtime_settings()
    backend = get_ai_backend(reasoning_effort=reasoning_effort, model=model)
    # Generation provenance is server-side audit metadata.  Keep it in the
    # database log, but never send it to the model as part of the teaching
    # contract or prompt input.
    generation_audit = payload.get("_generation_audit")
    backend_payload = {key: value for key, value in payload.items() if key != "_generation_audit"}
    logged_payload = {
        **backend_payload,
        "reasoning_effort": reasoning_effort,
        "experiment_spec_version": CURRENT_EXPERIMENT_SPEC_VERSION,
        "protocol_id": CURRENT_PROTOCOL_ID,
        "model": model,
        "study_settings_reference": {
            "model": STUDY_MODEL,
            "reasoning_effort": STUDY_REASONING_EFFORT,
        },
        "study_settings_match": model == STUDY_MODEL and reasoning_effort == STUDY_REASONING_EFFORT,
        "question_route_version": SHARED_QUESTION_ROUTE_VERSION,
        "interaction_history_audit": interaction_history_audit(backend_payload),
        "input_projection": project_model_payload(backend_payload, proposed=backend_payload.get("group_condition", "proposed") == "proposed", feedback=purpose != "generate_tutoring_turn"),
    }
    if generation_audit is not None:
        logged_payload["generation_audit"] = generation_audit
    started = datetime.now(UTC)
    try:
        result = await getattr(backend, purpose)(backend_payload)
        raw_text = getattr(result, "raw_text", None)
        request_audit = getattr(result, "request_audit", None)
        result = dict(result)
        latency = int((datetime.now(UTC) - started).total_seconds() * 1000)
        if purpose == "generate_tutoring_turn":
            result["output_metrics"] = _tutoring_output_metrics(result)
        if request_audit is not None:
            logged_payload["effective_request"] = _effective_request_with_instruction_audit(
                request_audit,
                generation_audit if isinstance(generation_audit, dict) else None,
            )
        _record_ai_log(
            db,
            AICallLog(
                provider=backend.provider,
                fallback_provider=result.pop("_fallback_provider", None),
                purpose=purpose,
                request_payload=logged_payload,
                response_payload=result,
                raw_text=raw_text,
                status="success",
                latency_ms=latency,
            ),
        )
        return result
    except CodexAppServerError as exc:
        latency = int((datetime.now(UTC) - started).total_seconds() * 1000)
        if exc.request_audit is not None:
            logged_payload["effective_request"] = _effective_request_with_instruction_audit(
                exc.request_audit,
                generation_audit if isinstance(generation_audit, dict) else None,
            )
        _record_ai_log(
            db,
            AICallLog(
                provider=getattr(backend, "provider", "unknown"),
                purpose=purpose,
                request_payload=logged_payload,
                raw_text=exc.raw_text,
                status="failed",
                error_code=exc.code,
                error_message=exc.detail,
                latency_ms=latency,
            ),
        )
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": exc.code,
                "message": exc.user_message,
                "hint": "ルート`.env`のCODEX_APP_SERVER_URLとCODEX_APP_SERVER_LISTEN_URLを確認し、scripts/start-codex-app-server.shまたは.ps1でCodex app-serverを起動して、Codex/ChatGPTログイン状態を確認してください。",
            },
        ) from exc
    except Exception as exc:
        request_audit = getattr(exc, "request_audit", None)
        if request_audit is not None:
            logged_payload["effective_request"] = _effective_request_with_instruction_audit(
                request_audit,
                generation_audit if isinstance(generation_audit, dict) else None,
            )
        _record_ai_log(
            db,
            AICallLog(
                provider=getattr(backend, "provider", "unknown"),
                purpose=purpose,
                request_payload=logged_payload,
                status="failed",
                error_code="ai_call_failed",
                error_message=str(exc),
            ),
        )
        raise


def _record_ai_log(db: Session, log: AICallLog) -> None:
    """Keep AI logs in the owning idempotent transaction when one is active."""
    participant_id = (log.request_payload or {}).get("participant_id")
    if participant_id and db.query(Participant.id).filter_by(id=participant_id).with_for_update().first() is None:
        raise HTTPException(404, "被験者が見つかりません。")
    if db.info.get("defer_commits"):
        db.info.setdefault("deferred_ai_logs", []).append(log)
        return
    db.add(log)
    db.commit()


def _selected_options(db: Session, attempt: Attempt) -> list[QuestionOption]:
    option_ids = attempt.selected_option_ids or []
    if not option_ids:
        return []
    options = db.query(QuestionOption).filter(QuestionOption.id.in_(option_ids)).all()
    by_id = {option.id: option for option in options}
    return [by_id[option_id] for option_id in option_ids if option_id in by_id]


def _selected_option_label_text(options: list[QuestionOption]) -> str | None:
    return " / ".join(option.option_label for option in options) if options else None


def _fixed_attempt_result(options: list[QuestionOption]) -> dict[str, Any]:
    is_correct, misconception_type, status = _classify_selected_options(options)
    return {
        "is_correct": is_correct,
        "score": 1.0 if is_correct else 0.0,
        "diagnosed_status": status,
        "misconception_type": misconception_type,
        "diagnosis_confidence": 0.95,
        "natural_language_diagnosis": "正しい構造を選択できています。" if is_correct else ("基本知識が不足している可能性があります。" if status == "unknown" else "選択内容に誤った捉え方が含まれています。"),
        "recommended_teaching_strategy": None if is_correct else strategy_for(misconception_type, status, "proposed"),
    }


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
        score = 80 + term_order_bonus
        if attempt.misconception_type == "M3":
            score += 10
        return score, f"{attempt.misconception_type}を概念変化で確認"
    if attempt.diagnosed_status == "unknown":
        return 70 + term_order_bonus, "豊富化で基礎理解を確認"
    return 10 + term_order_bonus, "正解記録"


async def diagnose_pretest(db: Session, participant_id: str) -> int:
    participant = get_participant(db, participant_id, for_update=True)
    _assert_participant_active(participant)
    _assert_phase_available(participant, "pretest")
    attempts = db.query(Attempt).filter_by(participant_id=participant.id, phase="pretest").all()
    if not attempts:
        raise HTTPException(status_code=400, detail="pretest attempts not found")
    active_term_ids = {term.id for term in _active_test_terms(db)}
    if len(attempts) != len(active_term_ids) or {attempt.term_id for attempt in attempts} != active_term_ids:
        raise HTTPException(status_code=400, detail="pretest attempts are incomplete")
    if any(attempt.is_correct is not None for attempt in attempts):
        raise HTTPException(status_code=409, detail="pretest has already been diagnosed")

    scored_attempts: list[Attempt] = []
    for attempt in attempts:
        question = db.get(Question, attempt.question_id)
        if not question or "multi_select" not in question.question_type:
            raise HTTPException(status_code=400, detail="unsupported question type")
        result = _fixed_attempt_result(_selected_options(db, attempt))
        if participant.group_condition == "control":
            result["recommended_teaching_strategy"] = "general_explanation"
        attempt.is_correct = result["is_correct"]
        attempt.score = 1.0 if result["is_correct"] else 0.0
        attempt.diagnosed_status = result["diagnosed_status"]
        attempt.misconception_type = result["misconception_type"]
        attempt.misconception_confidence = result["diagnosis_confidence"]
        attempt.natural_language_diagnosis = result["natural_language_diagnosis"]
        state = db.query(LearnerState).filter_by(participant_id=participant.id, term_id=attempt.term_id).one_or_none()
        if not state:
            state = LearnerState(participant_id=participant.id, term_id=attempt.term_id, current_status=result["diagnosed_status"], primary_misconception=result["misconception_type"], teaching_strategy=result["recommended_teaching_strategy"], last_attempt_id=attempt.id, state_summary=result["natural_language_diagnosis"])
            db.add(state)
        scored_attempts.append(attempt)
    _commit(db)

    for attempt in scored_attempts:
        existing = db.query(TermAssignment).filter_by(participant_id=participant.id, term_id=attempt.term_id).one_or_none()
        score, reason = _priority(attempt)
        if not existing:
            db.add(TermAssignment(participant_id=participant.id, term_id=attempt.term_id, group_condition=participant.group_condition, priority_score=score, selection_reason=reason))
        else:
            existing.priority_score = score
            existing.selection_reason = reason
    _commit(db)

    assignments = (
        db.query(TermAssignment)
        .join(Term, TermAssignment.term_id == Term.id)
        .filter(
            TermAssignment.participant_id == participant.id,
            Term.is_active.is_(True),
            Term.slug.in_(PRETEST_TERM_SLUGS),
        )
        .order_by(Term.display_order.asc())
        .all()
    )
    latest_attempt_by_term = {attempt.term_id: attempt for attempt in scored_attempts}
    for index, assignment in enumerate(assignments):
        latest_attempt = latest_attempt_by_term.get(assignment.term_id)
        assignment.is_learning_target = bool(latest_attempt and not latest_attempt.is_correct and index < get_settings().max_learning_targets)
    remaining = sum(1 for assignment in assignments if assignment.is_learning_target)
    participant.current_step = "learning_targets" if remaining else "final_test"
    _commit(db)
    return remaining


def learning_targets(db: Session, participant_id: str) -> list[dict[str, Any]]:
    participant = get_participant(db, participant_id)
    rows = (
        db.query(TermAssignment, Term, LearnerState)
        .join(Term, TermAssignment.term_id == Term.id)
        .join(LearnerState, (LearnerState.term_id == Term.id) & (LearnerState.participant_id == participant.id))
        .filter(
            TermAssignment.participant_id == participant.id,
            TermAssignment.is_learning_target.is_(True),
            Term.is_active.is_(True),
            Term.slug.in_(PRETEST_TERM_SLUGS),
        )
        # Priority remains an analysis/selection value, but the participant
        # follows the same term order as the pretest and retest.
        .order_by(Term.display_order.asc())
        .all()
    )

    def learner_summary(state: LearnerState) -> str:
        if state.current_status == "unknown":
            return "基本知識が不足している可能性があります。"
        if participant.group_condition == "proposed":
            if state.primary_misconception == "M3":
                return "概念の分類や位置づけに関する捉え方を見直します。"
            if state.primary_misconception == "M1":
                return "概念についての個別の説明に関する捉え方を見直します。"
        return _public_summary(state.state_summary)

    def target_stage(state: LearnerState) -> str:
        return _learning_stage_label_for_state(state)

    return [
        {
            "term_slug": term.slug,
            "term_label": term.label,
            "summary_for_learner": learner_summary(state),
            "current_stage_for_display": target_stage(state),
        }
        for _, term, state in rows
    ]


def pretest_results(db: Session, participant_id: str) -> list[dict[str, Any]]:
    """Return participant-safe results for the completed pretest.

    The stored Attempt fields remain the source of truth. This projection deliberately
    omits misconception labels and other diagnostic details from the participant API.
    """
    participant = get_participant(db, participant_id)
    target_rows = learning_targets(db, participant_id)
    targets_by_slug = {row["term_slug"]: row for row in target_rows}
    terms = (
        db.query(Term)
        .filter(Term.slug.in_(PRETEST_TERM_SLUGS), Term.is_active.is_(True))
        .order_by(Term.display_order)
        .all()
    )
    attempts = (
        db.query(Attempt)
        .filter(Attempt.participant_id == participant.id, Attempt.phase == "pretest")
        .order_by(Attempt.created_at.desc(), Attempt.id.desc())
        .all()
    )
    latest_attempt_by_term: dict[str, Attempt] = {}
    for attempt in attempts:
        latest_attempt_by_term.setdefault(attempt.term_id, attempt)

    results: list[dict[str, Any]] = []
    for term in terms:
        attempt = latest_attempt_by_term.get(term.id)
        target = targets_by_slug.get(term.slug)
        if attempt is None:
            result_label = "未回答"
            result_summary = "事前テストの結果を確認できません。"
            is_correct: bool | None = None
        elif attempt.is_correct:
            result_label = "正解"
            result_summary = "正しい構造を選択できています。"
            is_correct = True
        else:
            result_label = "不正解"
            result_summary = target["summary_for_learner"] if target else (
                "基本知識が不足している可能性があります。"
                if attempt.diagnosed_status == "unknown"
                else "選択内容に誤った捉え方が含まれています。"
            )
            is_correct = False
        results.append(
            {
                "term_slug": term.slug,
                "term_label": term.label,
                "is_correct": is_correct,
                "result_label": result_label,
                "result_summary": result_summary,
                "is_learning_target": bool(target),
            }
        )
    return results


def _public_selected_options(db: Session, attempt: Attempt) -> list[dict[str, str]]:
    """Return only the option text the participant selected for a test result."""
    selected_ids = attempt.selected_option_ids or []
    selected_ids = [option_id for option_id in selected_ids if option_id]
    if not selected_ids:
        return []

    options = db.query(QuestionOption).filter(QuestionOption.id.in_(selected_ids)).all()
    options_by_id = {option.id: option for option in options}
    snapshots = {
        row.get("option_id"): row
        for row in (attempt.option_order_snapshot or [])
        if isinstance(row, dict) and row.get("option_id")
    }
    participant = db.get(Participant, attempt.participant_id)
    if can_resume(participant) and any(not (snapshots.get(oid) or {}).get("label") for oid in selected_ids):
        question = db.get(Question, attempt.question_id)
        for row in _displayed_options(db, participant, question):
            saved = {key: value for key, value in (snapshots.get(row["option_id"]) or {}).items() if value is not None}
            snapshots[row["option_id"]] = {**row, **saved}
    selected: list[dict[str, str]] = []
    for option_id in selected_ids:
        snapshot = snapshots.get(option_id)
        option = options_by_id.get(option_id)
        if snapshot:
            selected.append(
                {
                    "label": str(snapshot.get("label") or (option.option_label if option else "")),
                    "body": str(snapshot.get("body") or (option.body if option else "")),
                }
            )
        elif option:
            selected.append({"label": option.option_label, "body": option.body})
    return selected


def _test_result_question(
    db: Session,
    participant: Participant,
    term: Term,
    test_round: str,
    phase: str,
) -> Question | None:
    historical_banks = HISTORICAL_ASSESSMENT_BANK_VERSIONS.get(participant.experiment_spec_version)
    uses_scenario_bank = historical_banks is not None or participant.experiment_spec_version == CURRENT_EXPERIMENT_SPEC_VERSION
    expected_variant: str | None = None
    if test_round == "test":
        expected_variant = "pretest_v1"
    elif phase == "final_test":
        expected_variant = "retest_v1"
    elif phase == "retest":
        round_number = _round_number(test_round)
        if round_number is not None:
            has_final_test = not uses_scenario_bank and db.query(Attempt.id).filter_by(participant_id=participant.id, phase="final_test").first() is not None
            variant_number = max(
                1,
                min(
                    ASSESSMENT_VARIANT_COUNTS["retest"] if uses_scenario_bank else 5,
                    round_number - (1 if has_final_test else 0),
                ),
            )
            expected_variant = f"retest_v{variant_number}"

    query = (
        db.query(Question)
        .filter(
            Question.term_id == term.id,
            Question.phase == phase,
        )
        .order_by(Question.created_at.desc(), Question.variant_key)
    )
    if uses_scenario_bank:
        mode = question_set_mode(participant.question_set_mode)
        banks = historical_banks if historical_banks is not None else ASSESSMENT_BANK_VERSIONS
        bank_version = banks.get(mode)
        if bank_version is None:
            return None
        query = query.filter(Question.construct_key == assessment_construct_key(term.slug, phase, mode, bank_version=bank_version))
        if can_resume(participant):
            query = query.filter(Question.is_active.is_(True))
    else:
        bank_versions = set(ASSESSMENT_BANK_VERSIONS.values())
        for banks in HISTORICAL_ASSESSMENT_BANK_VERSIONS.values():
            bank_versions.update(banks.values())
        for bank_version in bank_versions:
            query = query.filter(~Question.construct_key.endswith(bank_version))
    candidates = query.all()
    if expected_variant:
        return next((question for question in candidates if question.variant_key == expected_variant), None)
    return candidates[0] if candidates else None


def latest_test_results(db: Session, participant_id: str) -> dict[str, Any]:
    """Return the latest test round without exposing the correct answer."""
    participant = get_participant(db, participant_id)
    attempts = (
        db.query(Attempt)
        .filter(Attempt.participant_id == participant.id, Attempt.phase.in_(TEST_PHASES))
        .all()
    )
    grouped: dict[str, list[Attempt]] = {}
    for attempt in attempts:
        grouped.setdefault(_attempt_test_round(attempt), []).append(attempt)
    if not grouped:
        return {"test_round": None, "test_round_label": None, "results": []}

    def event_key(attempt: Attempt) -> tuple[datetime, datetime, str]:
        return (attempt.answered_at or attempt.created_at, attempt.created_at, attempt.id)

    def round_key(test_round: str) -> tuple[Any, ...]:
        round_attempts = grouped[test_round]
        latest = max(round_attempts, key=event_key)
        return (*_round_sort_key(test_round, latest.phase, latest.attempt_index), event_key(latest))

    selected_round = max(grouped, key=round_key)
    selected_attempts = grouped[selected_round]
    latest_by_term: dict[str, Attempt] = {}
    for attempt in sorted(selected_attempts, key=event_key, reverse=True):
        latest_by_term.setdefault(attempt.term_id, attempt)
    latest_attempt = max(selected_attempts, key=event_key)
    result_phase = latest_attempt.phase
    targets_by_slug = {row["term_slug"]: row for row in learning_targets(db, participant_id)}
    results: list[dict[str, Any]] = []

    for term in _active_test_terms(db):
        attempt = latest_by_term.get(term.id)
        question = db.get(Question, attempt.question_id) if attempt else _test_result_question(db, participant, term, selected_round, result_phase)
        selected_options = _public_selected_options(db, attempt) if attempt else []
        is_correct = attempt.is_correct if attempt else None
        if is_correct is True:
            result_label = "正解"
        elif is_correct is False:
            result_label = "不正解"
        else:
            result_label = "未回答"
        results.append(
            {
                "term_slug": term.slug,
                "term_label": term.label,
                "question_body": (attempt.question_body_snapshot if attempt else None) or (question.body if question else None),
                "selected_options": selected_options,
                "is_correct": is_correct,
                "result_label": result_label,
                "is_learning_target": term.slug in targets_by_slug,
            }
        )

    return {
        "test_round": selected_round,
        "test_round_label": _test_round_display_label(selected_round),
        "results": results,
    }


def create_tutor_session(db: Session, participant_id: str, term_slug: str) -> TutorSession:
    participant = get_participant(db, participant_id, for_update=True)
    term = db.query(Term).filter_by(slug=term_slug).one_or_none()
    if not term or not term.is_active:
        raise HTTPException(status_code=404, detail="term not found")
    _assert_learning_available(participant)
    assignment = db.query(TermAssignment).filter_by(participant_id=participant.id, term_id=term.id).one_or_none()
    if participant.current_step == "learning_targets" and (not assignment or not assignment.is_learning_target):
        raise HTTPException(status_code=409, detail="この用語は現在の学習対象ではありません。")
    existing = (
        db.query(TutorSession)
        .filter_by(participant_id=participant.id, term_id=term.id, ended_at=None)
        .order_by(TutorSession.started_at.desc())
        .first()
    )
    if existing:
        return existing
    count = db.query(func.count(TutorSession.id)).filter_by(participant_id=participant.id, term_id=term.id).scalar() or 0
    session = TutorSession(participant_id=participant.id, term_id=term.id, session_index=count + 1, group_condition=participant.group_condition)
    db.add(session)
    _commit(db)
    db.refresh(session)
    return session


def _predicted_history_entry(turn: TutorTurn, predicted_answer: dict[str, Any]) -> dict[str, Any]:
    meta = _practice_meta(turn)
    grading = predicted_answer["grading_json"]
    stage = grading.get("learning_stage") or meta.get("learning_stage") or "conceptual_change"
    return {
        "turn_id": turn.id,
        "turn_index": turn.turn_index,
        "learning_stage": stage,
        "label": grading.get("component_term") or meta.get("component_term") or LEARNING_STAGE_LABELS.get(stage, "概念変化"),
        "component_term": grading.get("component_term") or meta.get("component_term"),
        "misconception_type": grading.get("learning_misconception_type"),
        "confidence": grading.get("learning_misconception_confidence"),
        "reason": grading.get("learning_misconception_reason"),
        "is_sufficient": grading.get("is_sufficient"),
    }


def _tutoring_generation_context(
    db: Session,
    session: TutorSession,
    participant: Participant,
    *,
    predicted_answer: dict[str, Any] | None = None,
    generation_origin: str = "interactive",
    prefetch_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the shared generation contract without mutating answer state."""
    assert_current_experiment(participant)
    term = db.get(Term, session.term_id)
    if not term:
        raise HTTPException(status_code=404, detail="term not found")
    state = db.query(LearnerState).filter_by(participant_id=participant.id, term_id=term.id).one()
    pretest_attempt = None
    if participant.group_condition == "proposed":
        pretest_attempt = (
            db.query(Attempt)
            .filter_by(participant_id=participant.id, term_id=term.id, phase="pretest")
            .order_by(Attempt.created_at.desc(), Attempt.attempt_index.desc())
            .first()
        )
    turn_count = db.query(func.count(TutorTurn.id)).filter_by(tutor_session_id=session.id).scalar() or 0
    turn_index = turn_count + 1
    learning_variant_index = min(max(session.session_index, 1), LEARNING_SESSION_VARIANT_COUNT)
    position = _learning_position(db, session, term, participant)
    misconception_history = session_misconception_history(db, session.id) if participant.group_condition == "proposed" else []
    state_current_status = state.current_status
    state_primary_misconception = state.primary_misconception

    if predicted_answer is not None:
        # Project the fixed grading result without writing it before feedback
        # generation succeeds. The detached turn is used only for prompt text.
        predicted_stage = predicted_answer.get("next_learning_stage")
        if predicted_stage not in {"enrichment", "conceptual_change"}:
            raise HTTPException(status_code=400, detail="invalid next learning stage")
        position = {
            **position,
            "learning_stage": predicted_stage,
            "learning_stage_label": LEARNING_STAGE_LABELS[predicted_stage],
        }
        if participant.group_condition == "proposed":
            misconception_history = [
                *misconception_history,
                _predicted_history_entry(predicted_answer["turn"], predicted_answer),
            ]
            state_current_status = predicted_answer["diagnosed_status"]
            state_primary_misconception = predicted_answer["learning_misconception_type"]

    if position["learning_stage"] == "final_feedback":
        raise HTTPException(status_code=400, detail="learning session already completed")

    if participant.group_condition == "control":
        previous_learning_misconception = None
        effective_misconception = None
        effective_status = None
        effective_strategy = "general_explanation"
        active_misconception_type = None
    else:
        previous_learning_misconception = misconception_history[-1] if misconception_history else None
        effective_misconception = (previous_learning_misconception or {}).get("misconception_type") or state_primary_misconception
        effective_status = "unknown" if effective_misconception == "unknown" else ("misconception" if effective_misconception else state_current_status)
        effective_strategy = strategy_for(effective_misconception, effective_status, participant.group_condition)
        active_misconception_type = effective_misconception
        if not active_misconception_type and position["learning_stage"] == "enrichment":
            active_misconception_type = "unknown"

    mode = question_set_mode(participant.question_set_mode)
    learning_content_version = participant.learning_content_version
    spec = _learning_question_spec(
        term.slug,
        position["learning_stage"],
        learning_variant_index,
        mode,
        content_version=learning_content_version,
    )
    previous_turn = (
        db.query(TutorTurn)
        .filter_by(tutor_session_id=session.id)
        .order_by(TutorTurn.turn_index.desc())
        .first()
    )
    previous_question = previous_turn.practice_question_json if previous_turn else None
    saved_options = (
        previous_question.get("options")
        if isinstance(previous_question, dict)
        and previous_question.get("learning_variant_index") == learning_variant_index
        else None
    )
    practice_question = {
        "body": spec["body"],
        "question_type": spec["question_type"],
        "options": saved_options or _public_learning_options(
            spec,
            participant,
            term.slug,
            position["learning_stage"],
            learning_variant_index,
        ),
        "selection_mode": spec.get("selection_mode", "multiple"),
        "min_selections": spec.get("min_selections", 3),
        "max_selections": spec.get("max_selections", 3),
        "variant_key": spec["variant_key"],
        "learning_variant_index": learning_variant_index,
        "question_set_mode": mode,
        "learning_content_version": learning_content_version,
    }
    common_payload = {
        **explanation_context(mode),
        "question_set_mode": mode,
        "participant_id": participant.id,
        "group_condition": participant.group_condition,
        "term": {"slug": term.slug, "label": term.label, "description": term.description},
        "component_terms": _component_terms(term.slug, term.label),
        "prompt_contract_version": PROMPT_CONTRACT_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "rag_context": _rag_context(
            term.slug,
            term.label,
            term.description,
        ),
        "interaction_history": build_interaction_history(db, participant.id, term.id, projected_answer=predicted_answer),
    }
    if participant.group_condition == "proposed":
        selected_pretest_options = _selected_options(db, pretest_attempt) if pretest_attempt else []
        pretest_targets = _pretest_teaching_targets(term.slug, selected_pretest_options, mode)
        primary_pretest_target = _primary_pretest_target(pretest_targets, active_misconception_type)
        diagnostic_options = [
            {
                "label": option.option_label,
                "body": option.body,
                "initial_misconception_type": option.misconception_type,
                "claim_id": next(
                    (target["claim_id"] for target in pretest_targets if target["option_label"] == option.option_label),
                    None,
                ),
            }
            for option in selected_pretest_options
        ] if pretest_attempt else []
        payload = {
            **common_payload,
            "learning_stage": position["learning_stage"],
            "learning_stage_label": position["learning_stage_label"],
            "taxonomy_version": TAXONOMY_VERSION,
            "prompt_contract_version": PROMPT_CONTRACT_VERSION,
            "pretest_target": primary_pretest_target,
            "pretest_targets": pretest_targets,
            "learner_state": {
                "current_status": state_current_status,
                "primary_misconception": state_primary_misconception,
                "teaching_strategy": effective_strategy,
                "recurrence_count": state.recurrence_count,
            },
            "previous_diagnosis_for_learner": state.state_summary,
            "previous_learning_misconception": previous_learning_misconception,
            "session_misconception_history": misconception_history,
            "misconception_teaching_guidance": _misconception_teaching_guidance(active_misconception_type),
            "misconception_taxonomy": taxonomy_for_prompt(),
            "active_misconception_type": active_misconception_type,
            "mandatory_teaching_elements": mandatory_element_requirements(active_misconception_type),
            "diagnostic_evidence": {
                "selected_options": diagnostic_options,
                "diagnosed_type": active_misconception_type,
                "pretest_targets": pretest_targets,
            },
        }
    else:
        payload = common_payload
    instruction_route = "shared_history_diagnostic" if participant.group_condition == "proposed" else "shared_history_general"
    payload["_generation_audit"] = {
        "question_set_mode": mode,
        "assessment_bank_version": ASSESSMENT_BANK_VERSIONS[mode],
        "origin": generation_origin,
        "prefetch": prefetch_audit,
        "instruction_route": instruction_route,
        "question_route_version": SHARED_QUESTION_ROUTE_VERSION,
        "interaction_history": interaction_history_audit(payload),
        "term_slug": term.slug,
        "session_index": session.session_index,
        "turn_index": turn_index,
        "problem_variant_key": spec["variant_key"],
        "problem_variant_index": learning_variant_index,
        "actual_ai_input": _actual_tutoring_input(payload, participant.group_condition),
        "learning_content_version": learning_content_version,
    }
    forbidden_material = [spec["expected_answer"], spec["body"]]
    forbidden_material.extend(
        option["body"] for option in spec.get("options") or [] if option.get("is_correct")
    )
    return {
        "session": session,
        "participant": participant,
        "term": term,
        "state": state,
        "position": position,
        "spec": spec,
        "practice_question": practice_question,
        "payload": payload,
        "forbidden_material": forbidden_material,
        "turn_count": turn_count,
        "turn_index": turn_index,
        "generation_origin": generation_origin,
        "prefetch_audit": prefetch_audit,
        "learning_content_version": learning_content_version,
    }


def _build_tutor_turn_plan(
    db: Session,
    session: TutorSession,
    participant: Participant,
    *,
    predicted_answer: dict[str, Any],
) -> TutorTurnGenerationPlan:
    """Freeze a projected next-turn request before the answer transaction commits."""
    context = _tutoring_generation_context(
        db,
        session,
        participant,
        predicted_answer=predicted_answer,
        generation_origin="same_session_prefetch",
    )
    return TutorTurnGenerationPlan(
        session_id=session.id,
        participant_id=participant.id,
        group_condition=participant.group_condition,
        turn_index=context["turn_count"] + 1,
        learner_prompt=context["spec"]["body"],
        practice_question=_merge_stage_meta(context["practice_question"], context["position"]),
        position=context["position"],
        payload=context["payload"],
        forbidden_material=context["forbidden_material"],
        generation_origin=context["generation_origin"],
        prefetch_audit=context.get("prefetch_audit"),
        learning_content_version=context["learning_content_version"],
    )


def _tutor_turn_from_generation(
    context: dict[str, Any] | TutorTurnGenerationPlan,
    result: dict[str, Any],
    mandatory_validation: dict[str, Any],
    *,
    material_generation_ms: int,
) -> TutorTurn:
    if isinstance(context, TutorTurnGenerationPlan):
        session_id = context.session_id
        group_condition = context.group_condition
        position = context.position
        learner_prompt = context.learner_prompt
        practice_question = context.practice_question
        turn_index = context.turn_index
        generation_origin = context.generation_origin
        prefetch_audit = context.prefetch_audit
        payload = context.payload
        learning_content_version = context.learning_content_version
    else:
        session_id = context["session"].id
        group_condition = context["participant"].group_condition
        position = context["position"]
        learner_prompt = context["spec"]["body"]
        practice_question = context["practice_question"]
        turn_index = context["turn_count"] + 1
        generation_origin = context.get("generation_origin", "interactive")
        prefetch_audit = context.get("prefetch_audit")
        payload = context["payload"]
        learning_content_version = context["learning_content_version"]
    instruction_audit = dict(payload.get("_generation_audit") or {})
    diagnosis = {
        "material_glossary": glossary_snapshot(result["tutor_message"]),
        "material_source": "ai",
        "material_generation_ms": material_generation_ms,
        "mandatory_elements": result.get("mandatory_elements"),
        "mandatory_elements_validation": mandatory_validation,
        "teaching_contract": result.get("teaching_contract"),
        "teaching_contract_validation": mandatory_validation.get("teaching_contract"),
        "material_length_validation": mandatory_validation.get("material_length"),
        "material_structure_validation": mandatory_validation.get("material_structure"),
        "generation_attempts": mandatory_validation.get("attempts"),
        "tutoring_output_metrics": result.get("output_metrics") or _tutoring_output_metrics(result),
        "group_condition": group_condition,
        "taxonomy_version": payload.get("taxonomy_version"),
        "prompt_contract_version": payload.get("prompt_contract_version"),
        "learning_content_version": learning_content_version,
        "generation_origin": generation_origin,
        "question_set_mode": instruction_audit.get("question_set_mode", STANDARD),
        "prefetch": prefetch_audit or {"state": "not_applicable", "reused": False},
        "instruction_route": instruction_audit.get("instruction_route"),
        "question_route_version": SHARED_QUESTION_ROUTE_VERSION,
        "interaction_history": interaction_history_audit(payload),
        "instruction_audit": instruction_audit,
    }
    return TutorTurn(
        tutor_session_id=session_id,
        turn_index=turn_index,
        teaching_strategy=result["teaching_strategy"],
        tutor_message=result["tutor_message"],
        learner_prompt=learner_prompt,
        practice_question_json=_merge_stage_meta(practice_question, position),
        diagnosis_json=diagnosis,
    )


def _prefetch_state(session: TutorSession) -> str:
    return session.prefetch_state or "none"


def _mark_prefetch_consumed(db: Session, session: TutorSession, turn: TutorTurn) -> None:
    consumed_at = now()
    session.prefetch_state = "consumed"
    session.prefetch_consumed_at = consumed_at
    diagnosis = dict(turn.diagnosis_json or {})
    prefetch = dict(diagnosis.get("prefetch") or {})
    prefetch.update({"state": "consumed", "reused": True, "consumed_at": consumed_at.isoformat()})
    diagnosis["prefetch"] = prefetch
    diagnosis["generation_origin"] = diagnosis.get("generation_origin") or "prefetch"
    turn.diagnosis_json = diagnosis
    _update_prefetch_ai_logs(db, session.id, disposition="consumed")
    _commit(db)


def _discard_prefetch_for_interactive_generation(
    db: Session,
    session: TutorSession,
    *,
    reason: str,
) -> dict[str, Any]:
    state_before = _prefetch_state(session)
    discarded_at = now()
    session.prefetch_state = "discarded"
    session.prefetch_discarded_at = discarded_at
    session.prefetch_error_code = reason
    # This transition must be visible to the worker before the synchronous
    # fallback awaits the AI, otherwise the worker could insert a stale v1.
    db.commit()
    return {
        "state_before": state_before,
        "state": "discarded",
        "source_session_id": session.prefetch_source_session_id,
        "waited": state_before in {"pending", "generating"},
        "reused": False,
        "discarded": True,
        "reason": reason,
        "discarded_at": discarded_at.isoformat(),
    }


async def generate_tutor_turn(db: Session, session_id: str) -> TutorTurn:
    session = db.get(TutorSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    participant = get_participant(db, session.participant_id, for_update=True)
    session = db.query(TutorSession).filter_by(id=session_id).with_for_update().one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    _assert_participant_active(participant)
    if session.ended_at is not None:
        raise HTTPException(status_code=409, detail="学習セッションは終了しています。")

    latest_open_turn = (
        db.query(TutorTurn)
        .filter_by(tutor_session_id=session.id, learner_response=None)
        .order_by(TutorTurn.turn_index.desc(), TutorTurn.created_at.desc())
        .first()
    )
    if latest_open_turn:
        if _prefetch_state(session) == "ready":
            _mark_prefetch_consumed(db, session, latest_open_turn)
        return latest_open_turn

    turn_count = db.query(func.count(TutorTurn.id)).filter_by(tutor_session_id=session.id).scalar() or 0
    prefetch_audit = None
    state = _prefetch_state(session)
    if state in PREFETCH_WAITING_STATES:
        transition_audit = _discard_prefetch_for_interactive_generation(
            db,
            session,
            reason="interactive_generation_started",
        )
        # A prefetch is only a candidate for the first turn (v1).  If this
        # session already has a turn, keep the normal interactive audit for
        # subsequent adaptive turns even if a stale worker state remains.
        if turn_count == 0:
            prefetch_audit = transition_audit
        # The commit above expires the locked objects but retains the same
        # Session; subsequent reads use the current database snapshot.
        session = db.get(TutorSession, session_id)
        participant = get_participant(db, participant.id, for_update=True)
    elif turn_count == 0 and state in {"failed", "discarded"} and session.prefetch_source_session_id:
        prefetch_audit = {
            "state_before": state,
            "state": state,
            "source_session_id": session.prefetch_source_session_id,
            "waited": False,
            "reused": False,
            "discarded": state == "discarded",
            "reason": session.prefetch_error_code or "prefetch_unavailable",
        }

    context = _tutoring_generation_context(
        db,
        session,
        participant,
        generation_origin="interactive_fallback" if prefetch_audit else "interactive",
        prefetch_audit=prefetch_audit,
    )
    started = perf_counter()
    result, mandatory_validation = await _generate_validated_tutoring_turn(
        db,
        context["payload"],
        forbidden_strings=context["forbidden_material"],
    )
    turn = _tutor_turn_from_generation(
        context,
        result,
        mandatory_validation,
        material_generation_ms=int((perf_counter() - started) * 1000),
    )
    db.add(turn)
    _commit(db)
    db.refresh(turn)
    return turn


async def _run_tutor_turn_prefetch(handle: PrefetchHandle, plan: TutorTurnGenerationPlan) -> None:
    """Generate early and publish only after the answer request commits."""
    db = SessionLocal()
    try:
        assert_current_experiment(get_participant(db, plan.participant_id))
        started = perf_counter()
        result, mandatory_validation = await _generate_validated_tutoring_turn(
            db,
            plan.payload,
            forbidden_strings=plan.forbidden_material,
        )
        material_generation_ms = int((perf_counter() - started) * 1000)
        if not await handle.wait_for_decision():
            return

        db.expire_all()
        assert_current_experiment(get_participant(db, plan.participant_id))
        session = db.query(TutorSession).filter_by(id=plan.session_id).with_for_update().one_or_none()
        if session is None or session.ended_at is not None:
            return
        open_turn = (
            db.query(TutorTurn)
            .filter_by(tutor_session_id=plan.session_id, learner_response=None)
            .order_by(TutorTurn.turn_index.desc(), TutorTurn.created_at.desc())
            .first()
        )
        if open_turn is not None:
            return
        turn = _tutor_turn_from_generation(
            plan,
            result,
            mandatory_validation,
            material_generation_ms=material_generation_ms,
        )
        db.add(turn)
        db.commit()
    except asyncio.CancelledError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
def prepare_prefetch_sessions(db: Session, participant_id: str, source_session_id: str) -> list[str]:
    """Create open pending sessions for every later learning target.

    This function only performs short database work.  It deliberately does
    not call the AI backend; each returned session is generated independently
    by the response-after worker.
    """
    participant = get_participant(db, participant_id)
    assert_current_experiment(participant)
    source_session = db.get(TutorSession, source_session_id)
    if not source_session or source_session.participant_id != participant.id or source_session.ended_at is not None:
        return []
    if participant.current_step != "learning_targets":
        return []

    source_term = db.get(Term, source_session.term_id)
    source_order = PRETEST_TERM_ORDER.get(source_term.slug if source_term else "", -1)
    target_rows = learning_targets(db, participant.id)
    target_rows = sorted(
        (
            row for row in target_rows
            if PRETEST_TERM_ORDER.get(row["term_slug"], -1) > source_order
        ),
        key=lambda row: PRETEST_TERM_ORDER.get(row["term_slug"], 10_000),
    )
    prepared_ids: list[str] = []
    requested_at = now()
    for row in target_rows:
        term = db.query(Term).filter_by(slug=row["term_slug"]).one_or_none()
        if not term:
            continue
        existing = (
            db.query(TutorSession)
            .filter_by(participant_id=participant.id, term_id=term.id, ended_at=None)
            .order_by(TutorSession.started_at.desc())
            .first()
        )
        if existing:
            # A participant may have reached this term before the worker.  In
            # that case the interactive session wins and the worker must not
            # convert it into a prefetched session.
            if _prefetch_state(existing) == "pending" and existing.prefetch_source_session_id == source_session.id:
                prepared_ids.append(existing.id)
            continue
        count = db.query(func.count(TutorSession.id)).filter_by(participant_id=participant.id, term_id=term.id).scalar() or 0
        session = TutorSession(
            participant_id=participant.id,
            term_id=term.id,
            session_index=count + 1,
            group_condition=participant.group_condition,
            prefetch_state="pending",
            prefetch_source_session_id=source_session.id,
            prefetch_requested_at=requested_at,
        )
        db.add(session)
        db.flush()
        prepared_ids.append(session.id)
    if prepared_ids:
        db.commit()
    return prepared_ids


def _claim_prefetch_session(db: Session, session_id: str) -> bool:
    """Claim a pending session and release the transaction before AI awaits."""
    session = db.query(TutorSession).filter_by(id=session_id).with_for_update().one_or_none()
    if not session:
        return False
    participant = db.get(Participant, session.participant_id)
    if participant is not None:
        assert_current_experiment(participant)
    if _prefetch_state(session) != "pending" or session.ended_at is not None:
        return False
    assignment = db.query(TermAssignment).filter_by(participant_id=session.participant_id, term_id=session.term_id).one_or_none()
    if (
        not participant
        or participant.current_step != "learning_targets"
        or participant.completed_at is not None
        or not assignment
        or not assignment.is_learning_target
    ):
        session.prefetch_state = "discarded"
        session.prefetch_discarded_at = now()
        session.prefetch_error_code = "prefetch_not_current"
        session.ended_at = session.prefetch_discarded_at
        db.commit()
        return False
    session.prefetch_state = "generating"
    session.prefetch_generating_at = now()
    db.commit()
    return True


def _prefetch_generation_audit(session: TutorSession) -> dict[str, Any]:
    return {
        "state": "generating",
        "session_id": session.id,
        "source_session_id": session.prefetch_source_session_id,
        "generation_key": "initial-v1",
        "variant_policy": "v1",
        "waited": False,
        "reused": False,
        "discarded": False,
    }


def _prefetch_error_code(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if isinstance(detail, dict) and detail.get("error_code"):
            return str(detail["error_code"])
        return f"http_{exc.status_code}"
    return "prefetch_generation_failed"


def _update_prefetch_ai_logs(
    db: Session,
    session_id: str,
    *,
    disposition: str,
    error_code: str | None = None,
) -> None:
    """Attach the final lifecycle disposition to server-side AI audit rows."""
    logs = (
        db.query(AICallLog)
        .filter(
            AICallLog.purpose == "generate_tutoring_turn",
            AICallLog.request_payload["generation_audit"]["prefetch"]["session_id"].as_string() == session_id,
        )
        .all()
    )
    for log in logs:
        generation_audit = (log.request_payload or {}).get("generation_audit") or {}
        prefetch = generation_audit.get("prefetch") or {}
        if prefetch.get("session_id") != session_id:
            continue
        response = dict(log.response_payload or {})
        response["prefetch_audit"] = {
            "session_id": session_id,
            "disposition": disposition,
            "error_code": error_code,
            "reused": disposition == "consumed",
        }
        log.response_payload = response


def _prefetch_session_is_eligible(db: Session, session: TutorSession) -> bool:
    participant = db.get(Participant, session.participant_id)
    if participant is not None:
        assert_current_experiment(participant)
    assignment = db.query(TermAssignment).filter_by(participant_id=session.participant_id, term_id=session.term_id).one_or_none()
    return bool(
        participant
        and participant.current_step == "learning_targets"
        and participant.completed_at is None
        and assignment
        and assignment.is_learning_target
        and session.ended_at is None
    )


async def generate_prefetched_tutor_turn(db: Session, session_id: str) -> bool:
    """Generate and persist one prefetched v1 turn without holding user locks."""
    if not _claim_prefetch_session(db, session_id):
        return False
    session = db.get(TutorSession, session_id)
    if not session:
        return False
    participant = db.get(Participant, session.participant_id)
    if not participant:
        return False
    generation_audit = _prefetch_generation_audit(session)
    try:
        # The claim commit above is complete before this read/AI await.  No
        # participant or tutor-session row lock is held while the backend runs.
        context = _tutoring_generation_context(
            db,
            session,
            participant,
            generation_origin="prefetch",
            prefetch_audit=generation_audit,
        )
        started = perf_counter()

        async def operation() -> tuple[dict[str, Any], dict[str, Any]]:
            return await _generate_validated_tutoring_turn(
                db,
                context["payload"],
                forbidden_strings=context["forbidden_material"],
            )

        generated = await run_idempotent(
            db,
            scope=f"prefetch_tutor_turn:{session_id}",
            key="initial-v1",
            participant_id=participant.id,
            request_data={"session_id": session_id, "variant_policy": "v1"},
            operation=operation,
        )
        if isinstance(generated, list):
            result, mandatory_validation = generated
        else:
            result, mandatory_validation = generated
        generation_ms = int((perf_counter() - started) * 1000)

        db.expire_all()
        final_session = db.query(TutorSession).filter_by(id=session_id).with_for_update().one_or_none()
        if not final_session or _prefetch_state(final_session) != "generating":
            _update_prefetch_ai_logs(db, session_id, disposition="discarded", error_code="interactive_generation_won_race")
            db.commit()
            return False
        if not _prefetch_session_is_eligible(db, final_session):
            final_session.prefetch_state = "discarded"
            final_session.prefetch_discarded_at = now()
            final_session.prefetch_error_code = "prefetch_not_current"
            final_session.ended_at = final_session.prefetch_discarded_at
            _update_prefetch_ai_logs(db, session_id, disposition="discarded", error_code="prefetch_not_current")
            db.commit()
            return False
        existing_turn = db.query(TutorTurn).filter_by(tutor_session_id=session_id).first()
        if existing_turn:
            final_session.prefetch_state = "discarded"
            final_session.prefetch_discarded_at = now()
            final_session.prefetch_error_code = "interactive_turn_exists"
            _update_prefetch_ai_logs(db, session_id, disposition="discarded", error_code="interactive_turn_exists")
            db.commit()
            return False

        ready_audit = {
            **generation_audit,
            "state": "ready",
            "ready_at": now().isoformat(),
        }
        context["prefetch_audit"] = ready_audit
        turn = _tutor_turn_from_generation(
            context,
            result,
            mandatory_validation,
            material_generation_ms=generation_ms,
        )
        db.add(turn)
        final_session.prefetch_state = "ready"
        final_session.prefetch_ready_at = now()
        _update_prefetch_ai_logs(db, session_id, disposition="ready")
        db.commit()
        return True
    except Exception as exc:
        db.rollback()
        failed_session = db.query(TutorSession).filter_by(id=session_id).with_for_update().one_or_none()
        if failed_session:
            error_code = _prefetch_error_code(exc)
            if _prefetch_state(failed_session) == "generating":
                failed_session.prefetch_state = "failed"
                failed_session.prefetch_failed_at = now()
                failed_session.prefetch_error_code = error_code
            _update_prefetch_ai_logs(
                db,
                session_id,
                disposition="failed" if _prefetch_state(failed_session) == "failed" else "discarded",
                error_code=failed_session.prefetch_error_code or error_code,
            )
            db.commit()
        return False


def discard_unconsumed_prefetches(db: Session, participant_id: str, *, reason: str) -> int:
    assert_current_experiment(get_participant(db, participant_id))
    """Invalidate unused prefetched sessions at give-up and new rounds."""
    candidate_sessions = (
        db.query(TutorSession)
        .filter(
            TutorSession.participant_id == participant_id,
            TutorSession.ended_at.is_(None),
            TutorSession.prefetch_state.in_(sorted(PREFETCH_WAITING_STATES | {"failed", "discarded"})),
        )
        .all()
    )
    if not candidate_sessions:
        return 0

    # A failed/discarded prefetch session can continue as a normal interactive
    # session after synchronous fallback.  Only sessions whose turns are still
    # purely prefetched may be closed here; otherwise a new-round cleanup
    # would terminate an active learning session.
    candidate_ids = [session.id for session in candidate_sessions]
    turns = (
        db.query(TutorTurn)
        .filter(TutorTurn.tutor_session_id.in_(candidate_ids))
        .all()
    )
    interactive_session_ids = {
        turn.tutor_session_id
        for turn in turns
        if turn.learner_response is not None
        or turn.grading_json
        or (turn.diagnosis_json or {}).get("generation_origin") != "prefetch"
    }
    sessions = [session for session in candidate_sessions if session.id not in interactive_session_ids]
    discarded_at = now()
    for session in sessions:
        session.prefetch_state = "discarded"
        session.prefetch_discarded_at = discarded_at
        session.prefetch_error_code = reason
        session.ended_at = discarded_at
        _update_prefetch_ai_logs(db, session.id, disposition="discarded", error_code=reason)
    return len(sessions)

async def respond_tutor_turn(
    db: Session,
    turn_id: str,
    payload: dict[str, Any],
    *,
    prefetch_handle: PrefetchHandle | None = None,
) -> dict[str, Any]:
    turn = db.get(TutorTurn, turn_id)
    if not turn:
        raise HTTPException(status_code=404, detail="turn not found")
    session = db.get(TutorSession, turn.tutor_session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    participant = get_participant(db, session.participant_id, for_update=True)
    turn = db.query(TutorTurn).filter_by(id=turn_id).with_for_update().one_or_none()
    if not turn:
        raise HTTPException(status_code=404, detail="turn not found")
    session = db.get(TutorSession, turn.tutor_session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    _assert_participant_active(participant)
    if session.ended_at is not None:
        raise HTTPException(status_code=409, detail="学習セッションは終了しています。")
    if turn.learner_response is not None:
        raise idempotency_error(
            "answer_already_submitted",
            "この確認問題はすでに回答済みです。回答は変更できません。",
            turn_id=turn.id,
        )
    state = db.query(LearnerState).filter_by(participant_id=session.participant_id, term_id=session.term_id).one()
    response = ""
    term = db.get(Term, session.term_id)
    meta = _practice_meta(turn)
    learning_stage = meta.get("learning_stage") or "conceptual_change"
    variant_index = int((turn.practice_question_json or {}).get("learning_variant_index") or 1)

    spec = _learning_question_spec(
        term.slug,
        learning_stage,
        variant_index,
        question_set_mode(participant.question_set_mode),
        content_version=participant.learning_content_version,
    )
    selected_options = _selected_learning_options(
        spec,
        payload.get("selected_option_ids"),
        (turn.practice_question_json or {}).get("options"),
    )
    if spec.get("selection_mode") == "multiple":
        _validate_multi_select_options(selected_options, len(selected_options))
    displayed_options = (turn.practice_question_json or {}).get("options")
    if isinstance(displayed_options, list) and displayed_options:
        displayed_by_id = {
            str(option["option_id"]): option
            for option in displayed_options
            if isinstance(option, dict) and option.get("option_id")
        }
        selected_option_ids = payload.get("selected_option_ids") or []
        selected_displays = [displayed_by_id.get(str(option_id)) for option_id in selected_option_ids]
        if any(not option or not option.get("label") for option in selected_displays):
            raise HTTPException(status_code=400, detail="invalid selected options")
        feedback_options = [
            {**option, "label": display["label"]}
            for option, display in zip(selected_options, selected_displays, strict=True)
        ]
    else:
        displayed_labels = {
            option["body"]: option["label"]
            for option in _public_learning_options(spec, participant, term.slug, learning_stage, variant_index)
        }
        feedback_options = [
            {**option, "label": displayed_labels.get(option["body"], option["label"])}
            for option in selected_options
        ]
    result = _fixed_feedback_for_options(feedback_options, spec)
    response = result.get("selected_option_body") or response

    is_sufficient = bool(result.get("is_sufficient"))
    learning_misconception_type = result.get("learning_misconception_type")
    if learning_misconception_type not in {"M1", "M3", "unknown", None}:
        learning_misconception_type = "unknown"
    learning_misconception_confidence = result.get("learning_misconception_confidence")
    learning_misconception_reason = result.get("learning_misconception_reason") or result.get("state_update_reason") or ""
    diagnosed_status = "stable_correct" if is_sufficient else ("unknown" if learning_misconception_type == "unknown" else "misconception")
    stage_completed = is_sufficient
    next_learning_stage = "final_feedback" if is_sufficient else _learning_stage_for_misconception(learning_misconception_type, diagnosed_status)
    answered_turn_count = (
        db.query(TutorTurn)
        .filter_by(tutor_session_id=session.id)
        .filter(TutorTurn.learner_response.is_not(None))
        .count()
    )
    attempts_used = answered_turn_count + 1
    attempt_limit_reached = not is_sufficient and attempts_used >= get_settings().max_turns_per_term
    session_completed = is_sufficient or attempt_limit_reached
    next_action = "move_next" if session_completed else "continue"
    target_rows_before_completion = learning_targets(db, participant.id) if session_completed else []

    grading_json = {
        "is_sufficient": is_sufficient,
        "selected_option_ids": [str(option_id) for option_id in (payload.get("selected_option_ids") or [])],
        "selected_option_body": result.get("selected_option_body") or response,
        "learning_stage": learning_stage,
        "stage_completed": stage_completed,
        "next_learning_stage": next_learning_stage,
        "diagnosed_status": diagnosed_status,
        "learning_misconception_type": learning_misconception_type,
        "learning_misconception_confidence": learning_misconception_confidence,
        "learning_misconception_reason": learning_misconception_reason,
        "instruction_route": (turn.diagnosis_json or {}).get("instruction_route") or (
            "shared_history_diagnostic" if participant.group_condition == "proposed" else "shared_history_general"
        ),
        "question_route_version": SHARED_QUESTION_ROUTE_VERSION,
        "ai_next_action": result.get("next_action"),
        "response_time_sec": payload.get("response_time_sec"),
        "material_source": (turn.diagnosis_json or {}).get("material_source"),
        "material_generation_ms": (turn.diagnosis_json or {}).get("material_generation_ms"),
    }
    if prefetch_handle is not None and not is_sufficient and not attempt_limit_reached:
        prefetch_plan = _build_tutor_turn_plan(
            db,
            session,
            participant,
            predicted_answer={
                "turn": turn,
                "response": response,
                "grading_json": grading_json,
                "next_learning_stage": next_learning_stage,
                "diagnosed_status": diagnosed_status,
                "learning_misconception_type": learning_misconception_type,
                "timing": {
                    "question_shown_at": _naive_datetime(payload.get("question_shown_at")),
                    "answered_at": _naive_datetime(payload.get("answered_at")),
                    "response_time_sec": payload.get("response_time_sec"),
                },
            },
        )
        prefetch_handle.start(
            lambda worker_handle: _run_tutor_turn_prefetch(worker_handle, prefetch_plan)
        )

    selected_explanation_options = [
        option for option in selected_options if is_sufficient or not option.get("is_correct")
    ]
    selected_explanation_bodies = [option.get("body", "") for option in selected_explanation_options if option.get("body")]
    explanation_payload = {
        **explanation_context(participant.question_set_mode),
        "question_set_mode": question_set_mode(participant.question_set_mode),
        "participant_id": participant.id,
        "group_condition": participant.group_condition,
        "term": {"slug": term.slug, "label": term.label, "description": term.description},
        "component_terms": _component_terms(term.slug, term.label),
        "prompt_contract_version": PROMPT_CONTRACT_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "interaction_history": build_interaction_history(db, participant.id, term.id),
        "question_body": spec["body"],
        "selected_option_body": " / ".join(selected_explanation_bodies),
        "selected_option_bodies": selected_explanation_bodies,
        "material": turn.tutor_message or "",
        "rag_context": _rag_context(
            term.slug,
            term.label,
            term.description,
        ),
    }
    if participant.group_condition == "proposed":
        explanation_payload.update(
            {
                "learning_stage": learning_stage,
                "learner_state": {
                    "current_status": state.current_status,
                    "primary_misconception": state.primary_misconception,
                    "teaching_strategy": None if is_sufficient else strategy_for(learning_misconception_type, diagnosed_status, participant.group_condition),
                    "recurrence_count": state.recurrence_count,
                },
                "learning_misconception_type": learning_misconception_type,
                "misconception_teaching_guidance": _misconception_teaching_guidance(learning_misconception_type),
                "misconception_taxonomy": taxonomy_for_prompt(),
                "session_misconception_history": session_misconception_history(db, session.id),
            }
        )
    if is_sufficient:
        explanation_result = await _ai_call(db, "generate_correct_answer_summary", explanation_payload)
        feedback_text = explanation_result.get("summary") or ""
    else:
        explanation_result = await _ai_call(db, "explain_selected_distractor", explanation_payload)
        feedback_text = explanation_result.get("feedback") or ""
    if not feedback_text.strip():
        raise RuntimeError("AI explanation response was empty")

    grading_json["feedback_glossary"] = glossary_snapshot(feedback_text)
    turn.learner_response = response
    turn.question_shown_at = _naive_datetime(payload.get("question_shown_at"))
    turn.answered_at = _naive_datetime(payload.get("answered_at"))
    turn.response_time_sec = payload.get("response_time_sec")
    turn.ai_feedback = feedback_text
    turn.grading_json = grading_json
    state.stable_correct_count += 1 if is_sufficient else 0
    state.current_status = "stable_correct" if is_sufficient else diagnosed_status
    state.primary_misconception = None if is_sufficient else learning_misconception_type
    state.updated_reason = result["state_update_reason"]
    state.last_tutor_turn_id = turn.id
    next_url: str | None = None
    if session_completed:
        session.ended_at = now()
        assignment = db.query(TermAssignment).filter_by(participant_id=participant.id, term_id=session.term_id).one_or_none()
        if is_sufficient and assignment and assignment.is_learning_target:
            assignment.is_learning_target = False
            assignment.priority_score = 0
            assignment.selection_reason = "学習セッション完了"
        db.flush()
        current_target_index = next(
            (index for index, target in enumerate(target_rows_before_completion) if target["term_slug"] == term.slug),
            -1,
        )
        if current_target_index >= 0:
            # Use the pre-completion order: a successful current term is
            # removed from learning_targets() before the next URL is chosen.
            remaining_targets = target_rows_before_completion[current_target_index + 1:]
        else:
            current_order = PRETEST_TERM_ORDER.get(term.slug, -1)
            remaining_targets = [
                target
                for target in target_rows_before_completion
                if PRETEST_TERM_ORDER.get(target["term_slug"], -1) > current_order
            ]
        if remaining_targets:
            participant.current_step = "learning_targets"
            next_url = f"/learning/{remaining_targets[0]['term_slug']}"
        else:
            participant.current_step = "retest"
            next_url = "/retest"
    _commit(db)
    return {
        "feedback": turn.ai_feedback,
        "glossary": public_glossary(grading_json["feedback_glossary"]),
        "next_action": next_action,
        "is_sufficient": is_sufficient,
        "session_completed": session_completed,
        "learning_stage": learning_stage,
        "stage_completed": stage_completed,
        "next_learning_stage": next_learning_stage,
        "learning_misconception_type": learning_misconception_type,
        "learning_misconception_confidence": learning_misconception_confidence,
        "learning_misconception_reason": learning_misconception_reason,
        "turn_index": turn.turn_index,
        "max_turns": get_settings().max_turns_per_term,
        "attempts_used": attempts_used,
        "remaining_attempts": 0 if is_sufficient else max(get_settings().max_turns_per_term - attempts_used, 0),
        "session_ended_by_attempt_limit": attempt_limit_reached,
        "next_url": next_url,
    }

async def score_phase(db: Session, participant_id: str, phase: str) -> dict[str, Any]:
    participant = get_participant(db, participant_id, for_update=True)
    _assert_participant_active(participant)
    if phase not in {"retest", "final_test"}:
        raise HTTPException(status_code=400, detail="unsupported score phase")
    _assert_phase_available(participant, phase)
    expected_variant = _expected_test_variant(db, participant, phase)
    attempts = db.query(Attempt).filter_by(participant_id=participant.id, phase=phase, is_correct=None).all()
    if not attempts:
        raise HTTPException(status_code=400, detail=f"{phase} attempts not found")
    for attempt in attempts:
        question = db.get(Question, attempt.question_id)
        if not question or "multi_select" not in question.question_type:
            raise HTTPException(status_code=400, detail="unsupported question type")
        term = db.get(Term, question.term_id)
        if term is None:
            raise HTTPException(
                status_code=503,
                detail={
                    "error_code": "question_term_unavailable",
                    "message": "問題に対応する用語データが見つかりません。管理者に連絡してください。",
                },
            )
        if not question.is_active or question.variant_key != expected_variant or question.construct_key != assessment_construct_key(term.slug, phase, participant.question_set_mode):
            raise HTTPException(status_code=409, detail="この問題は今回のテスト対象ではありません。")
        result = _fixed_attempt_result(_selected_options(db, attempt))
        attempt.is_correct = result["is_correct"]
        attempt.score = result["score"]
        attempt.diagnosed_status = result["diagnosed_status"]
        attempt.misconception_type = result["misconception_type"]
        state = db.query(LearnerState).filter_by(participant_id=participant.id, term_id=attempt.term_id).one_or_none()
        if state is None:
            continue
        if phase == "retest":
            previous = db.query(Attempt).filter_by(participant_id=participant.id, term_id=attempt.term_id, phase="pretest").order_by(Attempt.created_at.desc()).first()
            if previous and previous.misconception_type in {"M1", "M3"} and previous.misconception_type == attempt.misconception_type:
                attempt.recurrence_flag = True
                state.recurrence_count += 1
                db.add(RecurrenceEvent(participant_id=participant.id, term_id=attempt.term_id, previous_attempt_id=previous.id, current_attempt_id=attempt.id, previous_misconception_type=previous.misconception_type, current_misconception_type=attempt.misconception_type, is_same_type=True, phase=phase))
        state.current_status = result["diagnosed_status"]
        state.primary_misconception = result["misconception_type"]
        state.teaching_strategy = ("general_explanation" if participant.group_condition == "control" else None) if attempt.is_correct else strategy_for(attempt.misconception_type, attempt.diagnosed_status, participant.group_condition)
        state.last_attempt_id = attempt.id
    db.flush()
    learning_target_slugs = _reset_test_learning_targets(db, participant, attempts)
    achieved_mastery = _is_mastery_test_batch(db, attempts)
    if phase == "retest":
        participant.retest_cycles_completed = (participant.retest_cycles_completed or 0) + 1
    retest_limit_reached = (
        not achieved_mastery
        and post_pretest_tests_completed(db, participant) >= MAX_POST_PRETEST_TESTS
    )
    if achieved_mastery or retest_limit_reached:
        participant.current_step = "survey"
        next_url = _next_url(participant.current_step)
    else:
        participant.current_step = "learning_targets"
        next_url = f"/learning/{learning_target_slugs[0]}" if learning_target_slugs else _next_url(participant.current_step)
    _commit(db)
    return {
        "status": "completed",
        "next_step": participant.current_step,
        "next_url": next_url,
        "learning_target_slugs": learning_target_slugs,
        "retest_cycles_completed": participant.retest_cycles_completed,
        **post_pretest_test_progress(db, participant),
        "retest_cycle_limit_reached": retest_limit_reached,
    }


def _next_url(step: str) -> str:
    return {
        "pretest": "/pretest",
        "learning_targets": "/learning-targets",
        "retest": "/retest",
        "final_test": "/final-test",
        "survey": "/survey",
        "finish": "/finish",
    }.get(step, "/start")


def _rate(items: list[Attempt], predicate) -> float | None:
    graded_items = [item for item in items if item.is_correct is not None]
    if not graded_items:
        return None
    return sum(1 for item in graded_items if predicate(item)) / len(graded_items)


def _active_test_terms(db: Session) -> list[Term]:
    return (
        db.query(Term)
        .filter(Term.slug.in_(PRETEST_TERM_SLUGS), Term.is_active.is_(True))
        .order_by(Term.display_order)
        .all()
    )


def _is_mastery_test_batch(db: Session, attempts: list[Attempt]) -> bool:
    active_term_ids = {term.id for term in _active_test_terms(db)}
    return (
        bool(active_term_ids)
        and len(attempts) == len(active_term_ids)
        and {attempt.term_id for attempt in attempts} == active_term_ids
        and all(attempt.is_correct is True for attempt in attempts)
    )


def _reset_test_learning_targets(db: Session, participant: Participant, attempts: list[Attempt]) -> list[str]:
    # A retest/final-test result starts a new learning-round decision.  Any
    # material prepared for the previous round is tied to stale learner state
    # and must not leak into the new round.
    discard_unconsumed_prefetches(db, participant.id, reason="new_learning_round")
    active_terms = _active_test_terms(db)
    active_term_ids = {term.id for term in active_terms}
    attempts_by_term: dict[str, list[Attempt]] = {term_id: [] for term_id in active_term_ids}
    for attempt in attempts:
        if attempt.term_id in attempts_by_term:
            attempts_by_term[attempt.term_id].append(attempt)

    assignments = {
        assignment.term_id: assignment
        for assignment in db.query(TermAssignment).filter_by(participant_id=participant.id).all()
    }
    for term in active_terms:
        assignment = assignments.get(term.id)
        if not assignment:
            assignment = TermAssignment(
                participant_id=participant.id,
                term_id=term.id,
                group_condition=participant.group_condition,
            )
            db.add(assignment)
            assignments[term.id] = assignment

        term_attempts = attempts_by_term[term.id]
        failed_attempt = next((attempt for attempt in term_attempts if attempt.is_correct is not True), None)
        if len(term_attempts) == 1 and failed_attempt is None:
            assignment.is_learning_target = False
            assignment.priority_score = 0
            assignment.selection_reason = "正解したため次周回から除外"
        elif failed_attempt:
            assignment.is_learning_target = True
            assignment.priority_score, assignment.selection_reason = _priority(failed_attempt)
        else:
            assignment.is_learning_target = True
            assignment.priority_score = 60
            assignment.selection_reason = "再テストの確認が不完全なため学習"

    db.flush()
    return [row["term_slug"] for row in learning_targets(db, participant.id)]


def _latest_retest_mastery_attempts(db: Session, attempts: list[Attempt]) -> list[Attempt]:
    active_terms = _active_test_terms(db)
    active_term_ids = {term.id for term in active_terms}
    latest_by_term: dict[str, Attempt] = {}
    for attempt in sorted(attempts, key=lambda item: (item.created_at, item.answered_at or item.created_at, item.id), reverse=True):
        if attempt.term_id in active_term_ids:
            latest_by_term.setdefault(attempt.term_id, attempt)
    if set(latest_by_term) != active_term_ids or not all(latest_by_term[term_id].is_correct is True for term_id in active_term_ids):
        return []
    return [latest_by_term[term.id] for term in active_terms]


def _round_number(test_round: str | None) -> int | None:
    match = re.fullmatch(r"retest_(\d+)", test_round or "")
    return int(match.group(1)) if match else None


def _round_label(phase: str, attempt_index: int) -> str:
    if phase == "pretest":
        return "test"
    if phase == "retest":
        return f"retest_{attempt_index}"
    if phase == "final_test":
        return "retest_1"
    return phase


def _attempt_test_round(attempt: Attempt) -> str:
    return attempt.test_round or _round_label(attempt.phase, attempt.attempt_index)


def _round_sort_key(test_round: str, phase: str, attempt_index: int) -> tuple[int, int, int]:
    if test_round == "test":
        return (0, 0, attempt_index)
    number = _round_number(test_round)
    if number is not None:
        return (1, number, attempt_index)
    phase_order = {}
    return (2, phase_order.get(phase, 99), attempt_index)


def _attempt_sort_key(attempt: Attempt) -> tuple[int, int, int, str]:
    return (*_round_sort_key(_attempt_test_round(attempt), attempt.phase, attempt.attempt_index), attempt.created_at.isoformat())


def _test_rounds(attempts: list[Attempt]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, int], list[Attempt]] = {}
    for attempt in attempts:
        if attempt.phase not in TEST_PHASES:
            continue
        grouped.setdefault((_attempt_test_round(attempt), attempt.phase, attempt.attempt_index), []).append(attempt)

    rows: list[dict[str, Any]] = []
    pretest_score: float | None = None
    previous_score: float | None = None
    for test_round, phase, attempt_index in sorted(grouped, key=lambda item: _round_sort_key(item[0], item[1], item[2])):
        items = grouped[(test_round, phase, attempt_index)]
        score_rate = _rate(items, lambda attempt: bool(attempt.is_correct))
        if phase == "pretest" and attempt_index == 1:
            pretest_score = score_rate
        incorrect_count = sum(1 for attempt in items if attempt.is_correct is False)
        row = {
            "round": test_round,
            "phase": phase,
            "attempt_index": attempt_index,
            "question_count": len(items),
            "correct_count": sum(1 for attempt in items if attempt.is_correct is True),
            "score_rate": score_rate,
            "score_delta_from_pretest_pt": None if score_rate is None or pretest_score is None else round((score_rate - pretest_score) * 100, 6),
            "score_delta_from_previous_test_pt": None if score_rate is None or previous_score is None else round((score_rate - previous_score) * 100, 6),
            "remaining_learning_target_count": incorrect_count if phase in {"pretest", "retest", "final_test"} else None,
            "event_time": _iso(max((attempt.answered_at or attempt.created_at for attempt in items), default=None)),
        }
        rows.append(row)
        if score_rate is not None:
            previous_score = score_rate
    return rows


def _misconception_value(attempt: Attempt) -> str | None:
    if attempt.is_correct:
        return None
    return attempt.misconception_type or attempt.diagnosed_status


def _misconception_change_type(initial: Attempt | None, latest: Attempt | None) -> str | None:
    if not initial or not latest:
        return None
    if latest.phase == "pretest":
        return None
    initial_m = _misconception_value(initial)
    latest_m = _misconception_value(latest)
    if initial.is_correct and latest.is_correct:
        return None
    if initial.is_correct and latest.is_correct is False:
        return "regressed"
    if not initial.is_correct and latest.is_correct:
        return "resolved"
    if initial_m == "unknown" and latest_m == "unknown":
        return "unknown_persisted"
    if initial_m in {"M1", "M3"} and latest_m == initial_m:
        return "same_type_recurred"
    if initial_m in {"M1", "M3"} and latest_m in {"M1", "M3"} and latest_m != initial_m:
        return "changed_type"
    return None


def _misconception_timeline(attempts: list[Attempt], terms: dict[str, Term]) -> dict[str, Any]:
    by_term: dict[str, list[Attempt]] = {}
    for attempt in attempts:
        if attempt.phase in TEST_PHASES:
            by_term.setdefault(attempt.term_id, []).append(attempt)

    terms_out: list[dict[str, Any]] = []
    for term_id, items in sorted(by_term.items(), key=lambda pair: terms.get(pair[0]).display_order if terms.get(pair[0]) else 99):
        ordered = sorted(items, key=_attempt_sort_key)
        initial = next((attempt for attempt in ordered if attempt.phase == "pretest"), ordered[0] if ordered else None)
        latest = ordered[-1] if ordered else None
        term = terms.get(term_id)
        terms_out.append(
            {
                "term_slug": term.slug if term else None,
                "term_label": term.label if term else None,
                "change_type": _misconception_change_type(initial, latest),
                "events": [
                    {
                        "round": _attempt_test_round(attempt),
                        "phase": attempt.phase,
                        "attempt_index": attempt.attempt_index,
                        "is_correct": attempt.is_correct,
                        "misconception_type": _misconception_value(attempt),
                        "diagnosed_status": attempt.diagnosed_status,
                        "recurrence_flag": attempt.recurrence_flag,
                        "event_time": _iso(attempt.answered_at or attempt.created_at),
                    }
                    for attempt in ordered
                ],
            }
        )
    return {"terms": terms_out}


def _learning_burden(db: Session, participant_id: str, attempts: list[Attempt]) -> dict[str, Any]:
    all_sessions = db.query(TutorSession).filter_by(participant_id=participant_id).all()
    session_ids = [session.id for session in all_sessions]
    all_turns = db.query(TutorTurn).filter(TutorTurn.tutor_session_id.in_(session_ids or ["__none__"])).all()
    turns_by_session: dict[str, list[TutorTurn]] = {}
    for turn in all_turns:
        turns_by_session.setdefault(turn.tutor_session_id, []).append(turn)

    def counts_as_learning(session: TutorSession) -> bool:
        state = _prefetch_state(session)
        if state not in PREFETCH_STATES:
            return True
        if state not in {"pending", "generating", "ready", "failed", "discarded"}:
            return True
        # A failed/discarded prefetch can still become a real interactive
        # session through synchronous fallback.  An untouched prefetched v1
        # has no answer and contributes neither burden nor answer history.
        for turn in turns_by_session.get(session.id, []):
            diagnosis = turn.diagnosis_json or {}
            if turn.learner_response is not None or turn.grading_json or diagnosis.get("generation_origin") != "prefetch":
                return True
        return False

    sessions = [session for session in all_sessions if counts_as_learning(session)]
    actual_session_ids = {session.id for session in sessions}
    turns = [turn for turn in all_turns if turn.tutor_session_id in actual_session_ids]
    retest_count = max(
        (_round_number(_attempt_test_round(attempt)) or 0 for attempt in attempts if attempt.phase in {"retest", "final_test"}),
        default=0,
    )
    test_time = sum(attempt.response_time_sec or 0 for attempt in attempts if attempt.phase in TEST_PHASES)
    learning_time = sum(turn.response_time_sec or 0 for turn in turns)
    retained_count = sum(1 for attempt in attempts if attempt.phase in {"pretest", "retest"} and attempt.is_correct is False)
    return {
        "retest_count": retest_count,
        "tutor_session_count": len(sessions),
        "tutor_turn_count": len(turns),
        "learning_target_retained_count": retained_count,
        "total_learning_time_sec": learning_time,
        "total_test_time_sec": test_time,
    }


def _condition_check(db: Session, participant: Participant, attempts: list[Attempt]) -> dict[str, Any]:
    sessions = db.query(TutorSession).filter_by(participant_id=participant.id).all()
    session_ids = [session.id for session in sessions]
    turns = db.query(TutorTurn).filter(TutorTurn.tutor_session_id.in_(session_ids or ["__none__"])).all()
    strategies = [turn.teaching_strategy for turn in turns if turn.teaching_strategy]
    return {
        "control_general_explanation_maintained": all(strategy == "general_explanation" for strategy in strategies) if participant.group_condition == "control" else None,
        "proposed_adaptive_strategy_used": any(strategy != "general_explanation" for strategy in strategies) if participant.group_condition == "proposed" else None,
    }


def recalculate_evaluation(db: Session, participant_id: str) -> EvaluationSummary:
    participant = get_participant(db, participant_id)
    assert_current_experiment(participant)
    attempts = db.query(Attempt).filter_by(participant_id=participant.id).all()
    by_phase = {phase: [a for a in attempts if a.phase == phase] for phase in TEST_PHASES}
    final_items = by_phase["final_test"]
    final_score_source = "final_test" if final_items else None
    retest_mastery_items = _latest_retest_mastery_attempts(db, by_phase["retest"])
    final_test_skipped = False
    if not final_items and retest_mastery_items:
        final_items = retest_mastery_items
        final_score_source = "retest_mastery"
        final_test_skipped = True
    initial_m = [a for a in by_phase["pretest"] if a.misconception_type in {"M1", "M3"}]
    same_rec = [a for a in by_phase["retest"] if a.recurrence_flag]
    def m_rate(m: str) -> float | None:
        denom = [a for a in initial_m if a.misconception_type == m]
        if not denom:
            return None
        rec_terms = {a.term_id for a in by_phase["retest"] if a.recurrence_flag and a.misconception_type == m}
        return len(rec_terms) / len(denom)

    def final_score_value(attempt: Attempt) -> bool:
        return bool(attempt.is_correct)

    condition_check = _condition_check(db, participant, attempts)
    condition_check.update(
        {
            "final_test_skipped_after_retest_mastery": final_test_skipped,
            "final_score_source": final_score_source,
        }
    )
    summary = EvaluationSummary(
        participant_id=participant.id,
        group_condition=participant.group_condition,
        pretest_score=_rate(by_phase["pretest"], lambda a: bool(a.is_correct)),
        retest_score=_rate(by_phase["retest"], lambda a: bool(a.is_correct)),
        attainment_correct_rate=_rate(final_items, final_score_value),
        same_misconception_recurrence_rate=(len(same_rec) / len(initial_m)) if initial_m else None,
        m1_recurrence_rate=m_rate("M1"),
        m3_recurrence_rate=m_rate("M3"),
        learning_target_count=db.query(func.count(TermAssignment.id)).filter_by(participant_id=participant.id, is_learning_target=True).scalar() or 0,
        score_timeline_json={
            "rounds": _test_rounds(attempts),
            "final_test_skipped_after_retest_mastery": final_test_skipped,
            "final_score_source": final_score_source,
        },
        misconception_timeline_json=_misconception_timeline(attempts, _term_map(db)),
        learning_burden_json=_learning_burden(db, participant.id, attempts),
        condition_check_json=condition_check,
        hypothesis_metrics_json=participant_metrics(db, participant),
        completed=participant.completed_at is not None and participant.completion_reason != "give_up",
    )
    db.add(summary)
    _commit(db)
    db.refresh(summary)
    return summary


def _has_scored_pretest(db: Session, participant_id: str) -> bool:
    active_term_ids = {term.id for term in _active_test_terms(db)}
    if not active_term_ids:
        return False
    attempts = db.query(Attempt).filter_by(participant_id=participant_id, phase="pretest").all()
    attempts_by_term: dict[str, list[Attempt]] = {term_id: [] for term_id in active_term_ids}
    for attempt in attempts:
        if attempt.term_id in attempts_by_term:
            attempts_by_term[attempt.term_id].append(attempt)
    return bool(attempts_by_term) and all(
        term_attempts and all(attempt.is_correct is not None for attempt in term_attempts)
        for term_attempts in attempts_by_term.values()
    )


def _latest_evaluation_source_at(db: Session, participant: Participant) -> datetime | None:
    timestamps = [participant.updated_at]
    source_queries = [
        (Attempt, Attempt.updated_at),
        (LearnerState, LearnerState.updated_at),
        (TermAssignment, TermAssignment.created_at),
        (RecurrenceEvent, RecurrenceEvent.created_at),
        (TutorSession, TutorSession.created_at),
        (ParticipantSurvey, ParticipantSurvey.created_at),
    ]
    for model, timestamp_column in source_queries:
        value = db.query(func.max(timestamp_column)).filter(model.participant_id == participant.id).scalar()
        if value:
            timestamps.append(value)

    turn_value = (
        db.query(func.max(TutorTurn.updated_at))
        .join(TutorSession, TutorTurn.tutor_session_id == TutorSession.id)
        .filter(TutorSession.participant_id == participant.id)
        .scalar()
    )
    if turn_value:
        timestamps.append(turn_value)
    return max(timestamps) if timestamps else None


def _ensure_evaluation_summary(db: Session, participant: Participant) -> EvaluationSummary | None:
    latest = (
        db.query(EvaluationSummary)
        .filter_by(participant_id=participant.id)
        .order_by(EvaluationSummary.created_at.desc(), EvaluationSummary.id.desc())
        .first()
    )
    if not can_resume(participant) or not _has_scored_pretest(db, participant.id):
        return latest
    source_at = _latest_evaluation_source_at(db, participant)
    expected_completed = participant.completed_at is not None and participant.completion_reason != "give_up"
    if (
        latest is None
        or (latest.hypothesis_metrics_json or {}).get("metrics_version") != METRICS_VERSION
        or (source_at is not None and latest.created_at < source_at)
        or latest.completed != expected_completed
    ):
        return recalculate_evaluation(db, participant.id)
    return latest


MISCONCEPTION_TRANSITION_TYPES = (
    "resolved",
    "same_type_recurred",
    "changed_type",
    "unknown_persisted",
    "regressed",
    "unclassified",
)


def _group_misconception_transition_summary(
    group_participants: list[Participant],
    latest_summaries: list[EvaluationSummary],
    terms: dict[str, Term],
) -> dict[str, Any]:
    summaries_by_participant = {summary.participant_id: summary for summary in latest_summaries}
    active_terms = sorted(
        (term for term in terms.values() if term.slug in PRETEST_TERM_SLUGS),
        key=lambda term: term.display_order,
    )
    output_terms: list[dict[str, Any]] = []

    for term in active_terms:
        counts = {transition_type: 0 for transition_type in MISCONCEPTION_TRANSITION_TYPES}
        eligible_count = 0
        for participant in group_participants:
            summary = summaries_by_participant.get(participant.id)
            timeline_terms = (summary.misconception_timeline_json or {}).get("terms", []) if summary else []
            term_timeline = next((row for row in timeline_terms if row.get("term_slug") == term.slug), None)
            events = (term_timeline or {}).get("events", [])
            if not any(event.get("phase") == "pretest" for event in events):
                continue
            eligible_count += 1
            change_type = (term_timeline or {}).get("change_type") or "unclassified"
            if change_type not in counts:
                change_type = "unclassified"
            counts[change_type] += 1

        rates = {
            transition_type: counts[transition_type] / eligible_count if eligible_count else 0
            for transition_type in MISCONCEPTION_TRANSITION_TYPES
        }
        output_terms.append(
            {
                "term_slug": term.slug,
                "term_label": term.label,
                "eligible_count": eligible_count,
                "missing_count": max(len(group_participants) - eligible_count, 0),
                "counts": counts,
                "rates": rates,
            }
        )

    return {"terms": output_terms}


def admin_summary(db: Session, mode: str = STANDARD) -> dict[str, Any]:
    mode = question_set_mode(mode)
    participants = db.query(Participant).filter_by(experiment_spec_version=CURRENT_EXPERIMENT_SPEC_VERSION, protocol_id=CURRENT_PROTOCOL_ID, consent_checked=True).all()
    participants = [p for p in participants if question_set_mode(p.question_set_mode) == mode]
    terms = _term_map(db)
    rows = []
    for group in ["control", "proposed"]:
        group_participants = [p for p in participants if p.group_condition == group]
        latest_summaries = []
        for p in group_participants:
            s = _ensure_evaluation_summary(db, p)
            if s:
                latest_summaries.append(s)
        def avg(attr: str):
            vals = [getattr(s, attr) for s in latest_summaries if getattr(s, attr) is not None]
            return sum(vals) / len(vals) if vals else None
        def avg_final_delta() -> float | None:
            vals = []
            for summary in latest_summaries:
                rounds = (summary.score_timeline_json or {}).get("rounds") or []
                final_round = next((row for row in reversed(rounds) if row.get("phase") in {"final_test"}), None)
                if final_round and final_round.get("score_delta_from_pretest_pt") is not None:
                    vals.append(final_round["score_delta_from_pretest_pt"])
                elif (summary.score_timeline_json or {}).get("final_score_source") == "retest_mastery" and summary.pretest_score is not None and summary.attainment_correct_rate is not None:
                    vals.append(round((summary.attainment_correct_rate - summary.pretest_score) * 100, 6))
            return sum(vals) / len(vals) if vals else None
        rows.append(
            {
                "group_condition": group,
                "participant_count": len(group_participants),
                "same_misconception_recurrence_rate": avg("same_misconception_recurrence_rate"),
                "attainment_correct_rate": avg("attainment_correct_rate"),
                "avg_score_delta_from_pretest_pt": avg_final_delta(),
                "misconception_transition_summary": _group_misconception_transition_summary(group_participants, latest_summaries, terms),
            }
        )
    return {"question_set_mode": mode, "groups": rows, "hypotheses": group_metrics(current_metrics(db, mode), mode)}


EXPORTS = {
    "participants": (Participant, ["id", "display_code", "group_condition", "assignment_method", "current_step", "started_at", "completed_at", "completion_reason"]),
    "attempts": (Attempt, ["id", "participant_id", "term_id", "phase", "test_round", "question_id", "legacy_selected_option_id", "selected_option_ids", "legacy_reason_text", "legacy_free_text_answer", "response_time_sec", "question_shown_at", "answered_at", "question_body_snapshot", "option_order_snapshot", "is_correct", "score", "diagnosed_status", "misconception_type", "recurrence_flag", "legacy_l0_success", "legacy_requires_manual_review", "created_at"]),
    "learner_states": (LearnerState, ["participant_id", "term_id", "current_status", "primary_misconception", "legacy_scaffolding_level", "teaching_strategy", "stable_correct_count", "recurrence_count", "legacy_l0_success_count", "updated_at"]),
    "tutor_sessions": (TutorSession, ["id", "participant_id", "term_id", "session_index", "group_condition", "started_at", "ended_at", "prefetch_state", "prefetch_source_session_id", "prefetch_requested_at", "prefetch_generating_at", "prefetch_ready_at", "prefetch_consumed_at", "prefetch_failed_at", "prefetch_discarded_at", "prefetch_error_code"]),
    "tutor_turns": (TutorTurn, ["id", "tutor_session_id", "turn_index", "legacy_scaffolding_level", "teaching_strategy", "legacy_strategy_changed", "tutor_message", "diagnosis_json", "practice_question_json", "learner_response", "ai_feedback", "legacy_next_scaffolding_level", "legacy_forbidden_help_given", "question_shown_at", "answered_at", "response_time_sec", "created_at"]),
    "recurrence_events": (RecurrenceEvent, ["id", "participant_id", "term_id", "previous_attempt_id", "current_attempt_id", "previous_misconception_type", "current_misconception_type", "is_same_type", "phase", "created_at"]),
    "ai_call_logs": (AICallLog, ["id", "provider", "fallback_provider", "purpose", "request_payload", "response_payload", "status", "error_code", "error_message", "latency_ms", "created_at"]),
    "evaluation_summary": (EvaluationSummary, ["participant_id", "group_condition", "pretest_score", "retest_score", "attainment_correct_rate", "same_misconception_recurrence_rate", "m1_recurrence_rate", "legacy_m2_recurrence_rate", "m3_recurrence_rate", "learning_target_count", "score_timeline_json", "misconception_timeline_json", "learning_burden_json", "condition_check_json", "completed", "created_at"]),
    "participant_surveys": (ParticipantSurvey, ["id", "participant_id", "phase", "ai_experience_level", "programming_experience_level", "llm_usage_level", "self_rated_ai_knowledge", "term_confidences", "usability_rating", "helpfulness_rating", "perceived_hint_amount", "free_comment", "created_at"]),
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
    selected_options = [options[option_id] for option_id in (attempt.selected_option_ids or []) if option_id in options]
    selected_option_body = _selected_option_label_text(selected_options)
    if selected_option_body is None and participant and not can_resume(participant):
        selected_option_body = legacy_selected_option_body(attempt, options)
    return {
        "attempt_id": attempt.id,
        "question_set_mode": question_set_mode(participant.question_set_mode) if participant else None,
        **({"legacy_fields": legacy_fields(attempt)} if participant and not can_resume(participant) else {}),
        "participant_id": attempt.participant_id,
        "display_code": participant.display_code if participant else None,
        "legacy_read_only": bool(participant and not can_resume(participant)),
        "group_condition": participant.group_condition if participant else None,
        "phase": attempt.phase,
        "test_round": _attempt_test_round(attempt),
        "term_slug": term.slug if term else None,
        "term_label": term.label if term else None,
        "question_body": attempt.question_body_snapshot or (question.body if question else None),
        "selected_option_body": selected_option_body,
        "selected_option_ids": attempt.selected_option_ids,
        "question_body_snapshot": attempt.question_body_snapshot,
        "option_order_snapshot": attempt.option_order_snapshot,
        "response_time_sec": attempt.response_time_sec,
        "question_shown_at": _iso(attempt.question_shown_at),
        "answered_at": _iso(attempt.answered_at),
        "is_correct": attempt.is_correct,
        "score": attempt.score,
        "diagnosed_status": attempt.diagnosed_status,
        "misconception_type": attempt.misconception_type,
        "recurrence_flag": attempt.recurrence_flag,
        "created_at": _iso(attempt.created_at),
    }


def _turn_log_row(turn: TutorTurn, session: TutorSession, participant: Participant | None, term: Term | None) -> dict[str, Any]:
    stage_meta = (turn.practice_question_json or {}).get("stage_meta") or {}
    grading = turn.grading_json or {}
    practice_question = turn.practice_question_json or {}
    diagnosis = turn.diagnosis_json or {}
    return {
        "tutor_turn_id": turn.id,
        "question_set_mode": question_set_mode(participant.question_set_mode) if participant else None,
        **({"legacy_fields": legacy_fields(turn)} if participant and not can_resume(participant) else {}),
        "tutor_session_id": turn.tutor_session_id,
        "participant_id": session.participant_id,
        "display_code": participant.display_code if participant else None,
        "legacy_read_only": bool(participant and not can_resume(participant)),
        "group_condition": session.group_condition,
        "term_slug": term.slug if term else None,
        "term_label": term.label if term else None,
        "session_index": session.session_index,
        "turn_index": turn.turn_index,
        "learning_stage": stage_meta.get("learning_stage"),
        "learning_stage_label": stage_meta.get("learning_stage_label"),
        "component_term": stage_meta.get("component_term"),
        "next_learning_stage": grading.get("next_learning_stage"),
        "teaching_strategy": turn.teaching_strategy,
        "mandatory_elements": (turn.diagnosis_json or {}).get("mandatory_elements"),
        "mandatory_elements_validation": (turn.diagnosis_json or {}).get("mandatory_elements_validation"),
        "teaching_contract": (turn.diagnosis_json or {}).get("teaching_contract"),
        "teaching_contract_validation": (turn.diagnosis_json or {}).get("teaching_contract_validation"),
        "material_structure_validation": (turn.diagnosis_json or {}).get("material_structure_validation"),
        "taxonomy_version": (turn.diagnosis_json or {}).get("taxonomy_version"),
        "prompt_contract_version": (turn.diagnosis_json or {}).get("prompt_contract_version"),
        "learning_content_version": diagnosis.get("learning_content_version"),
        "generation_origin": diagnosis.get("generation_origin"),
        "prefetch_audit": diagnosis.get("prefetch"),
        "prefetch_state": _prefetch_state(session),
        "prefetch_source_session_id": session.prefetch_source_session_id,
        "tutor_message": turn.tutor_message,
        "material_glossary": diagnosis.get("material_glossary"),
        "learner_prompt": turn.learner_prompt,
        "question_body": practice_question.get("body"),
        "selected_option_body": grading.get("selected_option_body"),
        "learner_response": turn.learner_response,
        "is_sufficient": grading.get("is_sufficient"),
        "learning_misconception_type": grading.get("learning_misconception_type"),
        "ai_feedback": turn.ai_feedback,
        "feedback_glossary": grading.get("feedback_glossary"),
        "practice_question": practice_question,
        "grading_json": turn.grading_json,
        "response_time_sec": turn.response_time_sec if turn.response_time_sec is not None else grading.get("response_time_sec"),
        "question_shown_at": _iso(turn.question_shown_at),
        "material_viewed_at": _iso(turn.material_viewed_at),
        "answered_at": _iso(turn.answered_at),
        "created_at": _iso(turn.created_at),
    }


def _answer_event_time(row: dict[str, Any]) -> str:
    return row.get("answered_at") or row.get("created_at") or ""


def _answer_history_attempt_row(attempt_row: dict[str, Any]) -> dict[str, Any]:
    return {
        **attempt_row,
        "answer_log_id": f"attempt:{attempt_row['attempt_id']}",
        "source_type": "test_attempt",
        "source_id": attempt_row["attempt_id"],
        "learning_stage": None,
        "turn_index": None,
        "is_sufficient": None,
        "teaching_strategy": None,
        "learner_response": attempt_row.get("selected_option_body") or (attempt_row.get("legacy_fields") or {}).get("free_text_answer") or (attempt_row.get("legacy_fields") or {}).get("reason_text"),
    }


def _answer_history_turn_row(turn_row: dict[str, Any]) -> dict[str, Any]:
    return {
        **turn_row,
        "answer_log_id": f"tutor_turn:{turn_row['tutor_turn_id']}",
        "source_type": "learning_turn",
        "source_id": turn_row["tutor_turn_id"],
        "phase": "learning",
        "is_correct": None,
        "misconception_type": turn_row.get("learning_misconception_type"),
        "recurrence_flag": None,
        "question_body_snapshot": turn_row.get("question_body"),
        "option_order_snapshot": (turn_row.get("practice_question") or {}).get("options"),
        "learner_response": turn_row.get("selected_option_body") or turn_row.get("learner_response"),
    }


def _answer_history_turn_rows(turn_row: dict[str, Any]) -> list[dict[str, Any]]:
    if turn_row.get("legacy_read_only"):
        rows = legacy_turn_answer_rows(turn_row)
        if rows:
            return rows
    return [_answer_history_turn_row(turn_row)]


def _answer_history_rows(attempt_rows: list[dict[str, Any]], turn_rows: list[dict[str, Any]], *, reverse: bool = False, limit: int | None = None) -> list[dict[str, Any]]:
    rows = [_answer_history_attempt_row(row) for row in attempt_rows]
    for row in turn_rows:
        if not row.get("learner_response") and not row.get("grading_json"):
            continue
        rows.extend(_answer_history_turn_rows(row))
    rows.sort(key=_answer_event_time, reverse=reverse)
    return rows[:limit] if limit is not None else rows


def _ai_log_belongs_to(log: AICallLog, participant_id: str) -> bool:
    payload = log.request_payload or {}
    return payload.get("participant_id") == participant_id


def _ai_log_group_condition(log: AICallLog, participants: dict[str, Participant]) -> str | None:
    participant_id = (log.request_payload or {}).get("participant_id")
    participant = participants.get(participant_id)
    return participant.group_condition if participant else None


def admin_logs_overview(db: Session, mode: str = STANDARD) -> dict[str, Any]:
    participants = db.query(Participant).order_by(Participant.created_at.desc()).all()
    participant_by_id = {participant.id: participant for participant in participants}
    give_up_counts = participant_give_up_counts(db, list(participant_by_id))
    groups = admin_summary(db, mode)["groups"]
    terms = _term_map(db)
    questions = _question_map(db)
    options = _option_map(db)
    attempts = db.query(Attempt).order_by(Attempt.created_at.desc()).limit(50).all()
    sessions = {session.id: session for session in db.query(TutorSession).all()}
    recent_turns = db.query(TutorTurn).order_by(TutorTurn.created_at.desc()).limit(30).all()
    ai_logs = db.query(AICallLog).order_by(AICallLog.created_at.desc()).limit(50).all()
    recurrences = db.query(RecurrenceEvent).order_by(RecurrenceEvent.created_at.desc()).limit(30).all()
    audit_events = (
        db.query(AuditEvent)
        .filter(AuditEvent.entity_type == "participant")
        .order_by(AuditEvent.created_at.desc())
        .limit(50)
        .all()
    )
    summary_rows = db.query(EvaluationSummary).order_by(EvaluationSummary.created_at.desc(), EvaluationSummary.id.desc()).all()
    latest_summaries: dict[str, EvaluationSummary] = {}
    for summary in summary_rows:
        latest_summaries.setdefault(summary.participant_id, summary)
    summaries = list(latest_summaries.values())
    recent_attempt_rows = [_attempt_log_row(row, participant_by_id, terms, questions, options) for row in attempts]
    recent_turn_rows = [
        _turn_log_row(row, sessions[row.tutor_session_id], participant_by_id.get(sessions[row.tutor_session_id].participant_id), terms.get(sessions[row.tutor_session_id].term_id))
        for row in recent_turns
        if row.tutor_session_id in sessions
    ]
    return {
        "participant_count": len(participants),
        "groups": groups,
        "participants": [
            {
                "participant_id": row.id,
                "display_code": row.display_code,
                "experiment_spec_version": row.experiment_spec_version,
                "question_set_mode": question_set_mode(row.question_set_mode),
                "protocol_id": row.protocol_id,
                "can_resume": can_resume(row),
                "group_condition": row.group_condition,
                "current_step": row.current_step,
                "retest_cycles_completed": row.retest_cycles_completed,
                **post_pretest_test_progress(db, row),
                "completed_at": _iso(row.completed_at),
                "completion_reason": row.completion_reason,
                "give_up_learning_count": give_up_counts.get((row.id, "give_up_learning"), 0),
                "give_up_experiment_count": give_up_counts.get((row.id, "give_up_experiment"), 0),
                "created_at": _iso(row.created_at),
            }
            for row in participants
        ],
        "recent_attempts": recent_attempt_rows,
        "recent_tutor_turns": recent_turn_rows,
        "recent_answer_history": _answer_history_rows(recent_attempt_rows, recent_turn_rows, reverse=True, limit=50),
        "recent_ai_call_logs": [
            {
                "id": row.id,
                "provider": row.provider,
                "purpose": row.purpose,
                "status": row.status,
                "error_code": row.error_code,
                "error_message": row.error_message,
                "latency_ms": row.latency_ms,
                "generation_audit": (row.request_payload or {}).get("generation_audit"),
                "prefetch_audit": (row.response_payload or {}).get("prefetch_audit"),
                "group_condition": _ai_log_group_condition(row, participant_by_id),
                "created_at": _iso(row.created_at),
            }
            for row in ai_logs
        ],
        "recent_audit_events": [
            {
                "id": row.id,
                "participant_id": row.entity_id,
                "display_code": participant_by_id.get(row.entity_id).display_code if participant_by_id.get(row.entity_id) else None,
                "group_condition": participant_by_id.get(row.entity_id).group_condition if participant_by_id.get(row.entity_id) else None,
                "actor": row.actor,
                "action": row.action,
                "before_json": row.before_json,
                "after_json": row.after_json,
                "created_at": _iso(row.created_at),
            }
            for row in audit_events
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
                "group_condition": participant_by_id.get(row.participant_id).group_condition if participant_by_id.get(row.participant_id) else None,
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
                "question_set_mode": question_set_mode(participant_by_id[row.participant_id].question_set_mode) if row.participant_id in participant_by_id else None,
                "legacy_read_only": not can_resume(participant_by_id[row.participant_id]) if row.participant_id in participant_by_id else True,
                **({"legacy_fields": legacy_fields(row)} if participant_by_id.get(row.participant_id) and not can_resume(participant_by_id[row.participant_id]) else {}),
                "retest_score": row.retest_score,
                "attainment_correct_rate": row.attainment_correct_rate,
                "same_misconception_recurrence_rate": row.same_misconception_recurrence_rate,
                "score_timeline": row.score_timeline_json,
                "misconception_timeline": row.misconception_timeline_json,
                "learning_burden": row.learning_burden_json,
                "condition_check": row.condition_check_json,
                "hypothesis_metrics": row.hypothesis_metrics_json,
                "completed": row.completed,
                "completion_reason": participant_by_id.get(row.participant_id).completion_reason if participant_by_id.get(row.participant_id) else None,
                "created_at": _iso(row.created_at),
            }
            for row in summaries
        ],
    }


def participant_logs(db: Session, participant_id: str) -> dict[str, Any]:
    participant = get_participant(db, participant_id)
    summary = _ensure_evaluation_summary(db, participant)
    participants = {participant.id: participant}
    give_up_counts = participant_give_up_counts(db, [participant.id])
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
    surveys = db.query(ParticipantSurvey).filter_by(participant_id=participant.id).order_by(ParticipantSurvey.created_at).all()
    audit_events = (
        db.query(AuditEvent)
        .filter_by(entity_type="participant", entity_id=participant.id)
        .order_by(AuditEvent.created_at)
        .all()
    )
    ai_logs = [row for row in db.query(AICallLog).order_by(AICallLog.created_at).all() if _ai_log_belongs_to(row, participant.id)]
    attempt_rows = [_attempt_log_row(row, participants, terms, questions, options) for row in attempts]
    tutor_sessions = [
        {
            "tutor_session_id": session.id,
            "term_slug": terms.get(session.term_id).slug if terms.get(session.term_id) else None,
            "term_label": terms.get(session.term_id).label if terms.get(session.term_id) else None,
            "session_index": session.session_index,
            "group_condition": session.group_condition,
            "started_at": _iso(session.started_at),
            "ended_at": _iso(session.ended_at),
            "material_viewed_at": _iso(min((turn.material_viewed_at for turn in turns_by_session.get(session.id, []) if turn.material_viewed_at is not None), default=None)),
            "prefetch_state": _prefetch_state(session),
            "prefetch_source_session_id": session.prefetch_source_session_id,
            "prefetch_requested_at": _iso(session.prefetch_requested_at),
            "prefetch_generating_at": _iso(session.prefetch_generating_at),
            "prefetch_ready_at": _iso(session.prefetch_ready_at),
            "prefetch_consumed_at": _iso(session.prefetch_consumed_at),
            "prefetch_failed_at": _iso(session.prefetch_failed_at),
            "prefetch_discarded_at": _iso(session.prefetch_discarded_at),
            "prefetch_error_code": session.prefetch_error_code,
            "turns": [_turn_log_row(turn, session, participant, terms.get(session.term_id)) for turn in turns_by_session.get(session.id, [])],
        }
        for session in sessions
    ]
    turn_rows = [turn for session in tutor_sessions for turn in session["turns"]]
    return {
        "participant": {
            "participant_id": participant.id,
            "display_code": participant.display_code,
            "experiment_spec_version": participant.experiment_spec_version,
            "question_set_mode": question_set_mode(participant.question_set_mode),
            "learning_content_version": participant.learning_content_version,
            "protocol_id": participant.protocol_id,
            "can_resume": can_resume(participant),
            "group_condition": participant.group_condition,
            "assignment_method": participant.assignment_method,
            "consent_document_version": participant.consent_document_version,
            "consented_at": _iso(participant.consented_at),
            "current_step": participant.current_step,
            "retest_cycles_completed": participant.retest_cycles_completed,
            **post_pretest_test_progress(db, participant),
            "started_at": _iso(participant.started_at),
            "completed_at": _iso(participant.completed_at),
            "completion_reason": participant.completion_reason,
            "give_up_learning_count": give_up_counts.get((participant.id, "give_up_learning"), 0),
            "give_up_experiment_count": give_up_counts.get((participant.id, "give_up_experiment"), 0),
            "created_at": _iso(participant.created_at),
        },
        "attempts": attempt_rows,
        "answer_history": _answer_history_rows(attempt_rows, turn_rows),
        "learner_states": [
            {
                "term_slug": terms.get(row.term_id).slug if terms.get(row.term_id) else None,
                "term_label": terms.get(row.term_id).label if terms.get(row.term_id) else None,
                "current_status": row.current_status,
                **({"legacy_fields": legacy_fields(row)} if not can_resume(participant) else {}),
                "primary_misconception": row.primary_misconception,
                "current_stage_for_display": _learning_stage_label_for_state(row) if can_resume(participant) else "旧試用の保存値",
                "teaching_strategy": row.teaching_strategy,
                "stable_correct_count": row.stable_correct_count,
                "recurrence_count": row.recurrence_count,
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
        "tutor_sessions": tutor_sessions,
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
        "audit_events": [
            {
                "id": row.id,
                "actor": row.actor,
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "before_json": row.before_json,
                "after_json": row.after_json,
                "created_at": _iso(row.created_at),
            }
            for row in audit_events
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
                "raw_text": row.raw_text,
                "created_at": _iso(row.created_at),
            }
            for row in ai_logs
        ],
        "surveys": [
            {
                "id": row.id,
                "participant_id": row.participant_id,
                "phase": row.phase,
                "ai_experience_level": row.ai_experience_level,
                "survey_version": row.survey_version,
                "responses": row.responses_json,
                "programming_experience_level": row.programming_experience_level,
                "llm_usage_level": row.llm_usage_level,
                "self_rated_ai_knowledge": row.self_rated_ai_knowledge,
                "term_confidences": row.term_confidences,
                "usability_rating": row.usability_rating,
                "helpfulness_rating": row.helpfulness_rating,
                "perceived_hint_amount": row.perceived_hint_amount,
                "free_comment": row.free_comment,
                "created_at": _iso(row.created_at),
            }
            for row in surveys
        ],
        "latest_evaluation_summary": None
        if not summary
        else {
            "pretest_score": summary.pretest_score,
            **({"legacy_fields": legacy_fields(summary)} if not can_resume(participant) else {}),
            "retest_score": summary.retest_score,
            "attainment_correct_rate": summary.attainment_correct_rate,
            "same_misconception_recurrence_rate": summary.same_misconception_recurrence_rate,
            "m1_recurrence_rate": summary.m1_recurrence_rate,
            "m3_recurrence_rate": summary.m3_recurrence_rate,
            "learning_target_count": summary.learning_target_count,
            "score_timeline": summary.score_timeline_json,
            "misconception_timeline": summary.misconception_timeline_json,
            "learning_burden": summary.learning_burden_json,
            "condition_check": summary.condition_check_json,
            "hypothesis_metrics": summary.hypothesis_metrics_json,
            "completed": summary.completed,
            "completion_reason": participant.completion_reason,
            "created_at": _iso(summary.created_at),
        },
    }


LOG_CSV_COLUMNS = [
    "record_type",
    "source_type",
    "participant_id",
    "display_code",
    "phase",
    "test_round",
    "term_slug",
    "event_time",
    "question_shown_at",
    "answered_at",
    "response_time_sec",
    "question_body",
    "selected_option_body",
    "question_body_snapshot",
    "option_order_snapshot",
    "summary",
    "value_json",
]


def _csv_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _log_csv_rows_from_participant_logs(logs: dict[str, Any]) -> list[dict[str, Any]]:
    participant = logs["participant"]
    rows: list[dict[str, Any]] = []
    base = {"participant_id": participant["participant_id"], "display_code": participant["display_code"]}
    rows.append({**base, "record_type": "participant", "phase": "registration", "event_time": participant.get("created_at"), "summary": "participant protocol and completion metadata", "value_json": _csv_value(participant)})
    for answer in logs["answer_history"]:
        if answer["source_type"] == "test_attempt":
            summary = f"{answer['term_label']} {answer['phase']} correct={answer['is_correct']} m={answer['misconception_type']}"
        else:
            summary = f"{answer['term_label']} learning turn {answer['turn_index']} stage={answer['learning_stage']} component={answer['component_term']} sufficient={answer['is_sufficient']} strategy={answer['teaching_strategy']}"
        rows.append({**base, "record_type": "answer", "source_type": answer["source_type"], "phase": answer["phase"], "test_round": answer.get("test_round"), "term_slug": answer["term_slug"], "event_time": _answer_event_time(answer), "question_shown_at": answer.get("question_shown_at"), "answered_at": answer.get("answered_at"), "response_time_sec": answer.get("response_time_sec"), "question_body": answer.get("question_body"), "selected_option_body": answer.get("selected_option_body"), "question_body_snapshot": answer.get("question_body_snapshot"), "option_order_snapshot": _csv_value(answer.get("option_order_snapshot")), "summary": summary, "value_json": _csv_value(answer)})
    for state in logs["learner_states"]:
        rows.append({**base, "record_type": "learner_state", "phase": "state", "term_slug": state["term_slug"], "event_time": state["updated_at"], "summary": f"{state['term_label']} status={state['current_status']} stage={state['current_stage_for_display']} strategy={state['teaching_strategy']}", "value_json": _csv_value(state)})
    for session in logs["tutor_sessions"]:
        rows.append({**base, "record_type": "tutor_session", "phase": "learning", "term_slug": session["term_slug"], "event_time": session["started_at"], "summary": f"{session['term_label']} session {session['session_index']}", "value_json": _csv_value({k: v for k, v in session.items() if k != "turns"})})
    for event in logs["recurrence_events"]:
        rows.append({**base, "record_type": "recurrence", "phase": event["phase"], "term_slug": event["term_slug"], "event_time": event["created_at"], "summary": f"{event['previous_misconception_type']} -> {event['current_misconception_type']}", "value_json": _csv_value(event)})
    for event in logs["audit_events"]:
        rows.append({**base, "record_type": "audit_event", "phase": "control", "term_slug": "", "event_time": event["created_at"], "summary": f"{event['actor']} {event['action']}", "value_json": _csv_value(event)})
    for call in logs["ai_call_logs"]:
        rows.append({**base, "record_type": "ai_call", "phase": "", "term_slug": "", "event_time": call["created_at"], "summary": f"{call['purpose']} {call['status']} {call['error_code'] or ''}".strip(), "value_json": _csv_value(call)})
    for survey in logs["surveys"]:
        rows.append({**base, "record_type": "survey", "source_type": "survey", "phase": survey["phase"], "term_slug": "", "event_time": survey["created_at"], "summary": "post-experiment survey", "value_json": _csv_value(survey)})
    if logs["latest_evaluation_summary"]:
        summary = logs["latest_evaluation_summary"]
        summary_label = f"latest evaluation summary completed={summary['completed']} completion_reason={summary.get('completion_reason') or '-'}"
        rows.append({**base, "record_type": "evaluation_summary", "phase": "summary", "term_slug": "", "event_time": summary["created_at"], "summary": summary_label, "value_json": _csv_value(summary)})
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


def export_csv(db: Session, name: str, mode: str = STANDARD) -> Path:
    if name in {"hypothesis_metrics", "hypothesis_group_summary"}:
        mode = question_set_mode(mode)
        path = Path(get_settings().export_dir) / f"{name}_{mode}.csv"
        return write_metrics_csv(path, current_metrics(db, mode), grouped=name == "hypothesis_group_summary", mode=mode)
    if name not in EXPORTS:
        raise HTTPException(status_code=404, detail="unknown export")
    model, columns = EXPORTS[name]
    path = Path(get_settings().export_dir) / f"{name}.csv"
    rows = db.query(model).all()
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: _csv_value(getattr(row, col)) if isinstance(getattr(row, col), (dict, list)) else getattr(row, col) for col in columns})
    db.add(ExportJob(export_name=name, file_path=str(path), status="success", row_count=len(rows)))
    _commit(db)
    return path
