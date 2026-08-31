from __future__ import annotations

import csv
import json
import random
import re
from datetime import UTC, datetime
from time import perf_counter
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ai.codex_app_server_backend import CodexAppServerError
from app.ai.backend import lower_level, normalize_level, raise_level, strategy_for
from app.ai.factory import get_ai_backend
from app.ai.misconception_taxonomy import taxonomy_for_prompt
from app.core.config import get_settings
from app.rag.retriever import retrieve_rag_context
from app.seed.content_loader import content_term, learning_question_spec, load_content
from app.models import (
    AICallLog,
    AuditEvent,
    Attempt,
    EvaluationSummary,
    ExportJob,
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


PUBLIC_LEVEL = {"L3": "豊富化", "L2": "概念変化"}
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
FINAL_TEST_NOT_AVAILABLE_DETAIL = "この参加者は最終テスト対象ではありません。"


def _component_terms(term_slug: str, term_label: str) -> list[str]:
    try:
        return list(content_term(term_slug).get("component_terms") or [term_label])
    except StopIteration:
        return [term_label]


def _learning_question_spec(
    term_slug: str,
    learning_stage: str,
    component_term: str | None,
    variant_index: int = 1,
) -> dict[str, Any]:
    try:
        return learning_question_spec(term_slug, learning_stage, variant_index)
    except (KeyError, StopIteration) as exc:
        raise HTTPException(status_code=400, detail="fixed learning question not found") from exc


def _learning_question_item(term_slug: str, component_term: str) -> dict[str, Any]:
    spec = _learning_question_spec(term_slug, "conceptual_change", component_term)
    return {
        "component_term": component_term,
        "material": spec["material"],
        "body": spec["body"],
        "expected_answer": spec["expected_answer"],
        "question_type": spec["question_type"],
        "options": _public_learning_options(spec),
    }


def _public_learning_options(spec: dict[str, Any]) -> list[dict[str, str]]:
    return [{"option_id": option["option_id"], "label": option["label"], "body": option["body"]} for option in spec["options"]]


def _selection_constraints(question_type: str | None, option_count: int) -> dict[str, Any]:
    if question_type and "multi_select" in question_type:
        return {"selection_mode": "multiple", "min_selections": 3, "max_selections": 3}
    if option_count:
        return {"selection_mode": "single", "min_selections": 1, "max_selections": 1}
    return {"selection_mode": "free_text", "min_selections": 0, "max_selections": 0}


def _learning_option_meta(spec: dict[str, Any], option_id: str | None) -> dict[str, Any] | None:
    if not option_id:
        return None
    return next((option for option in spec["options"] if option["option_id"] == option_id), None)


def _selected_fixed_option(spec: dict[str, Any], selected_option_id: str | None, response: str) -> dict[str, Any] | None:
    option = _learning_option_meta(spec, selected_option_id)
    if option:
        return option
    cleaned = (response or "").strip()
    if not cleaned:
        return None
    return next((item for item in spec["options"] if item["body"] == cleaned), None)


def _selected_learning_options(spec: dict[str, Any], selected_option_ids: list[str] | None, selected_option_id: str | None, response: str) -> list[dict[str, Any]]:
    ids = selected_option_ids or ([selected_option_id] if selected_option_id else [])
    options = [_learning_option_meta(spec, option_id) for option_id in ids]
    selected = [option for option in options if option]
    if selected:
        return selected
    option = _selected_fixed_option(spec, selected_option_id, response)
    return [option] if option else []


def _selected_labels(options: list[dict[str, Any]]) -> str:
    return " / ".join(option["label"] for option in options)


def _option_label(option: Any) -> str | None:
    return option.option_label if hasattr(option, "option_label") else option.get("label")


def _option_misconception(option: Any) -> str | None:
    return option.misconception_type if hasattr(option, "misconception_type") else option.get("misconception_type")


def _validate_multi_select_labels(labels: set[str], selected_count: int) -> None:
    if labels == {"J"} and selected_count == 1:
        return
    if "J" in labels:
        raise HTTPException(status_code=400, detail="unknown option cannot be combined with other options")
    if not labels.issubset(set("ABCDEFGHI")) or selected_count != 3:
        raise HTTPException(status_code=400, detail="select exactly three options from A-I or only J")


def _classify_selected_options(options: list[Any], correct_labels: set[str] | None = None) -> tuple[bool, str | None, str]:
    selected_labels = {_option_label(option) for option in options}
    correct_labels = correct_labels or {"A", "B", "C"}
    misconceptions = [_option_misconception(option) for option in options]
    if "M3" in misconceptions:
        return False, "M3", "misconception"
    if "M1" in misconceptions:
        return False, "M1", "misconception"
    if selected_labels == correct_labels:
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
        "next_scaffolding_level": "L2" if is_correct else "L3",
        "learning_misconception_type": mtype,
        "learning_misconception_confidence": 0.95,
        "learning_misconception_reason": "固定3選択式問題で正解選択肢だけを選びました。" if is_correct else f"固定3選択式問題で{mtype}相当として判定しました。",
        "state_update_reason": "fixed_multi_select_correct" if is_correct else f"fixed_multi_select_{status}",
        "selected_option_body": selected_label_text,
    }


def _fixed_feedback(option: dict[str, Any] | None, spec: dict[str, Any]) -> dict[str, Any]:
    return _fixed_feedback_for_options([option] if option else [], spec)


def _fixed_item_result(component_term: str, selected_option_id: str | None, response: str, spec: dict[str, Any]) -> dict[str, Any]:
    option = _selected_fixed_option(spec, selected_option_id, response)
    correct_option = next((item for item in spec["options"] if item["is_correct"]), None)
    is_correct = bool(option and option["is_correct"])
    misconception_type = None if is_correct else ((option or {}).get("misconception_type") or "unknown")
    return {
        "component_term": component_term,
        "question_body": spec["body"],
        "selected_option_id": option.get("option_id") if option else selected_option_id,
        "selected_option_body": option.get("body") if option else response,
        "correct_option_id": correct_option.get("option_id") if correct_option else None,
        "correct_answer": correct_option.get("body") if correct_option else spec.get("expected_answer"),
        "is_correct": is_correct,
        "is_sufficient": is_correct,
        "learning_misconception_type": misconception_type,
        "feedback": "正解です。要点を押さえられています。" if is_correct else "不正解です。正解文と教材を確認して、次の確認で選び直してください。",
    }


def _feedback_text_from_item_results(item_results: list[dict[str, Any]]) -> str:
    lines = ["回答結果"]
    for item in item_results:
        status = "正解" if item["is_correct"] else "不正解"
        lines.append(f"【{item['component_term']}】{status}")
        lines.append(f"あなたの回答: {item.get('selected_option_body') or '未選択'}")
        lines.append(f"正解: {item.get('correct_answer') or ''}")
        lines.append(f"フィードバック: {item['feedback']}")
    return "\n".join(lines)


def _previous_turn_prefix(previous_turn: TutorTurn | None) -> str:
    if not previous_turn:
        return ""
    parts = []
    previous_question = (previous_turn.practice_question_json or {}).get("body")
    if previous_question:
        parts.append(f"前の問題: {previous_question}")
    if previous_turn.learner_response:
        parts.append(f"あなたの回答: {previous_turn.learner_response}")
    if previous_turn.ai_feedback:
        parts.append(f"前の回答を踏まえて、{previous_turn.ai_feedback}")
    return "\n".join(parts) + ("\n\n" if parts else "")


def _practice_question_text(practice_question: dict[str, Any] | None) -> str:
    if not practice_question:
        return ""
    if practice_question.get("body"):
        return practice_question["body"]
    items = practice_question.get("items") or []
    return " / ".join(item.get("body", "") for item in items if item.get("body"))


def _misconception_scaffolding_guidance(misconception_type: str | None) -> str:
    return {
        "M1": "単一の誤った命題を明示し、反証と正しい説明を対比して信念を置き換えさせる。",
        "M2": "複数の信念がつながった説明モデルを確認し、中核前提を修正してモデル全体を再構成させる。",
        "M3": "対象概念を誤った上位カテゴリーに置いていることへ気づかせ、正しいカテゴリーへ再分類させる。",
        "M4": "不足しているカテゴリーや関係のスキーマを具体例から構築し、新しい知識構造へ接続させる。",
        "unknown": "基礎定義と構成要素を短く確認し、最小限の判断基準を示す。",
    }.get(misconception_type, "現在の構成用語の定義、役割、判断基準を短く整理する。")


def _practice_meta(turn: TutorTurn | None) -> dict[str, Any]:
    if not turn or not isinstance(turn.practice_question_json, dict):
        return {}
    return turn.practice_question_json.get("stage_meta") or {}


def _learning_stage_for_misconception(misconception_type: str | None, status: str | None = None) -> str:
    return "enrichment" if misconception_type == "unknown" or status == "unknown" else "conceptual_change"


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
        "component_term": None,
        "component_index": 0,
        "component_total": 1,
        "component_terms": _component_terms(term.slug, term.label),
    }

def _merge_stage_meta(practice_question: dict[str, Any], position: dict[str, Any]) -> dict[str, Any]:
    practice_question = dict(practice_question or {})
    practice_question["stage_meta"] = {
        "learning_stage": position["learning_stage"],
        "learning_stage_label": position["learning_stage_label"],
        "component_term": position["component_term"],
        "component_index": position["component_index"],
        "component_total": position["component_total"],
        "component_terms": position.get("component_terms") or [],
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
        stage = grading.get("learning_stage") or meta.get("learning_stage") or "conceptual_change"
        item_results = grading.get("item_results") or []
        if item_results:
            for index, item in enumerate(item_results):
                history.append(
                    {
                        "turn_id": turn.id,
                        "turn_index": turn.turn_index,
                        "learning_stage": stage,
                        "label": item.get("component_term") or f"構成用語{index + 1}",
                        "component_term": item.get("component_term"),
                        "component_index": index,
                        "misconception_type": item.get("learning_misconception_type"),
                        "confidence": grading.get("learning_misconception_confidence"),
                        "reason": item.get("feedback") or grading.get("learning_misconception_reason"),
                        "is_sufficient": item.get("is_sufficient"),
                    }
                )
            continue
        label = grading.get("component_term") or meta.get("component_term") or LEARNING_STAGE_LABELS.get(stage, "概念変化")
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


def _rag_context(term_slug: str, *parts: str | None) -> dict[str, Any]:
    term_config = content_term(term_slug)
    return retrieve_rag_context(
        _rag_query(*parts),
        top_k=3,
        allowed_sections=term_config.get("rag_sections") or [],
        topic_slug=term_slug,
    )


def get_participant(db: Session, participant_id: str) -> Participant:
    participant = db.get(Participant, participant_id)
    if not participant:
        raise HTTPException(status_code=404, detail="participant not found")
    return participant


def next_display_code(db: Session) -> str:
    display_codes = db.query(Participant.display_code).all()
    max_number = 0
    for (display_code,) in display_codes:
        match = re.fullmatch(r"P(\d+)", display_code or "")
        if match:
            max_number = max(max_number, int(match.group(1)))
    return f"P{max_number + 1:03d}"


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


def delete_participant(db: Session, participant_id: str) -> dict[str, Any]:
    participant = get_participant(db, participant_id)
    session_ids = [session.id for session in db.query(TutorSession).filter_by(participant_id=participant.id).all()]
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
                "group_condition": participant.group_condition,
                "current_step": participant.current_step,
                "deleted_counts": deleted_counts,
            },
            after_json={"deleted": True},
        )
        db.add(audit)
        db.delete(participant)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {"participant_id": participant.id, "deleted": True, "deleted_counts": deleted_counts}



def _source_question_phase(phase: str) -> str:
    return phase


def _retest_variant_number(question: Question) -> int:
    match = re.fullmatch(r"retest_v(\d+)", question.variant_key or "")
    return int(match.group(1)) if match else 1


def _test_round_key_for_question(db: Session, participant: Participant, phase: str, question: Question) -> str | None:
    if phase == "pretest":
        return "test"
    if phase == "final_test":
        return "retest_1"
    if phase == "retest":
        has_final_test = db.query(Attempt.id).filter_by(participant_id=participant.id, phase="final_test").first() is not None
        offset = 1 if has_final_test else 0
        return f"retest_{_retest_variant_number(question) + offset}"
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
    if phase == "retest":
        previous_count = db.query(func.count(Attempt.id)).filter_by(
            participant_id=participant.id,
            term_id=term_id,
            phase="retest",
        ).scalar() or 0
        variant_number = min(previous_count + 1, 4)
        expected_key = f"retest_v{variant_number}"
    elif phase == "pretest":
        expected_key = "pretest_v1"
    elif phase == "final_test":
        expected_key = "final_test_v1"
    else:
        expected_key = "l0_check_v1"
    return next((question for question in candidates if question.variant_key == expected_key), candidates[0])


def _displayed_options(db: Session, participant: Participant, question: Question) -> list[dict[str, str]]:
    options = db.query(QuestionOption).filter(QuestionOption.question_id == question.id).order_by(QuestionOption.default_order).all()
    if not options:
        return []
    if "multi_select" in question.question_type:
        return [{"option_id": option.id, "label": option.option_label, "body": option.body} for option in options]
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
    public_options = []
    for index, option_id in enumerate(display.option_order):
        option = option_by_id[option_id]
        public_options.append({"option_id": option.id, "label": chr(65 + index), "body": option.body})
    return public_options


def question_payloads(db: Session, participant_id: str, phase: str) -> list[dict[str, Any]]:
    participant = get_participant(db, participant_id)
    if phase == "final_test" and participant.current_step != "final_test":
        raise HTTPException(status_code=409, detail=FINAL_TEST_NOT_AVAILABLE_DETAIL)
    all_questions = _question_query_for_phase(db, participant, phase).all()
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
    out = []
    for question in questions:
        term = db.get(Term, question.term_id)
        public_options = _displayed_options(db, participant, question)
        test_round = _test_round_key_for_question(db, participant, phase, question)
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
                "requires_reason": phase not in {"pretest", "retest", "final_test"},
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


def submit_attempt(db: Session, payload: dict[str, Any], idempotency_key: str | None = None) -> Attempt:
    question = db.get(Question, payload["question_id"])
    if not question:
        raise HTTPException(status_code=404, detail="question not found")
    participant = get_participant(db, payload["participant_id"])
    phase = payload.get("phase") or question.phase
    if idempotency_key:
        existing = db.query(Attempt).filter_by(participant_id=participant.id, idempotency_key=idempotency_key).one_or_none()
        if existing:
            return existing
    if phase == "final_test" and participant.current_step != "final_test":
        raise HTTPException(status_code=409, detail=FINAL_TEST_NOT_AVAILABLE_DETAIL)
    selected_option_ids = payload.get("selected_option_ids") or ([payload.get("selected_option_id")] if payload.get("selected_option_id") else [])
    selected_option_ids = [option_id for option_id in selected_option_ids if option_id]
    constraints = _selection_constraints(question.question_type, db.query(func.count(QuestionOption.id)).filter_by(question_id=question.id).scalar() or 0)
    if constraints["selection_mode"] == "multiple":
        selected_for_validation = db.query(QuestionOption).filter(QuestionOption.question_id == question.id, QuestionOption.id.in_(selected_option_ids or ["__none__"])).all()
        if len(selected_for_validation) != len(selected_option_ids):
            raise HTTPException(status_code=400, detail="invalid selected options")
        selected_labels = {option.option_label for option in selected_for_validation}
        _validate_multi_select_labels(selected_labels, len(selected_option_ids))
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
        test_round=_test_round_key_for_question(db, participant, phase, question),
        attempt_index=attempt_index,
        selected_option_id=(payload.get("selected_option_id") or (selected_option_ids[0] if selected_option_ids else None)),
        selected_option_ids=selected_option_ids or None,
        free_text_answer=None if is_pretest else payload.get("free_text_answer"),
        reason_text=None if is_pretest else payload.get("reason_text"),
        confidence=None,
        response_time_sec=payload.get("response_time_sec"),
        question_shown_at=_naive_datetime(payload.get("question_shown_at")),
        answered_at=_naive_datetime(payload.get("answered_at")),
        question_body_snapshot=_variant_body_for_round(db, participant.id, question, phase),
        option_order_snapshot=_displayed_options(db, participant, question),
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
                "hint": "ルート`.env`のCODEX_APP_SERVER_URLとCODEX_APP_SERVER_LISTEN_URLを確認し、scripts/start-codex-app-server.shまたは.ps1でCodex app-serverを起動して、Codex/ChatGPTログイン状態を確認してください。",
            },
        ) from exc
    except Exception as exc:
        db.add(AICallLog(provider=getattr(backend, "provider", "unknown"), purpose=purpose, request_payload=payload, status="failed", error_code="ai_call_failed", error_message=str(exc)))
        db.commit()
        raise


def _selected_option(db: Session, attempt: Attempt) -> QuestionOption | None:
    return db.get(QuestionOption, attempt.selected_option_id) if attempt.selected_option_id else None


def _selected_options(db: Session, attempt: Attempt) -> list[QuestionOption]:
    option_ids = attempt.selected_option_ids or ([attempt.selected_option_id] if attempt.selected_option_id else [])
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
        "secondary_misconception_type": None,
        "diagnosis_confidence": 0.95,
        "natural_language_diagnosis": "正しい構造を選択できています。" if is_correct else ("基本知識が不足している可能性があります。" if status == "unknown" else "選択内容に誤った捉え方が含まれています。"),
        "recommended_initial_scaffolding_level": "L2" if is_correct else "L3",
        "recommended_teaching_strategy": strategy_for(misconception_type, status, "proposed"),
        "requires_manual_review": False,
        "l0_success": is_correct,
    }


def _diagnosis_payload(db: Session, participant: Participant, attempt: Attempt) -> dict[str, Any]:
    question = db.get(Question, attempt.question_id)
    term = db.get(Term, attempt.term_id)
    option = _selected_option(db, attempt)
    options = _selected_options(db, attempt)
    payload = {
        "participant_id": participant.id,
        "group_condition": participant.group_condition,
        "term": {"slug": term.slug, "label": term.label, "definition": term.description},
        "question": {"id": question.id, "phase": question.phase, "question_type": question.question_type, "body": question.body, "expected_answer": question.expected_answer},
        "selected_option": None
        if not option
        else {"id": option.id, "body": option.body, "is_correct": option.is_correct, "initial_misconception_type": option.misconception_type},
        "selected_options": [
            {"id": item.id, "label": item.option_label, "body": item.body, "is_correct": item.is_correct, "initial_misconception_type": item.misconception_type}
            for item in options
        ],
        "history": {"previous_attempts": []},
    }
    if question.phase != "pretest":
        payload["learner_response"] = {"reason_text": attempt.reason_text, "free_text_answer": attempt.free_text_answer}
    if participant.group_condition == "proposed":
        payload["misconception_taxonomy"] = taxonomy_for_prompt()
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
        score = 80 + term_order_bonus
        if attempt.misconception_type == "M3":
            score += 10
        return score, f"{attempt.misconception_type}を概念変化で確認"
    if attempt.diagnosed_status == "unknown":
        return 70 + term_order_bonus, "豊富化で基礎理解を確認"
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
        question = db.get(Question, attempt.question_id)
        if question and "multi_select" in question.question_type:
            result = _fixed_attempt_result(_selected_options(db, attempt))
            if participant.group_condition == "control":
                result["recommended_teaching_strategy"] = "general_explanation"
        else:
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
        .filter(
            TermAssignment.participant_id == participant.id,
            TermAssignment.is_learning_target.is_(True),
            Term.is_active.is_(True),
            Term.slug.in_(PRETEST_TERM_SLUGS),
        )
        .order_by(TermAssignment.priority_score.desc(), Term.display_order.asc())
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
        if state.current_status == "misconception":
            return LEARNING_STAGE_LABELS["conceptual_change"]
        if state.current_status == "unknown":
            return LEARNING_STAGE_LABELS["enrichment"]
        return PUBLIC_LEVEL.get(normalize_level(state.scaffolding_level), "概念理解を確認")

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
    selected_ids = attempt.selected_option_ids or ([attempt.selected_option_id] if attempt.selected_option_id else [])
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
    expected_variant: str | None = None
    if test_round == "test":
        expected_variant = "pretest_v1"
    elif phase == "final_test":
        expected_variant = "final_test_v1"
    elif phase == "retest":
        round_number = _round_number(test_round)
        if round_number is not None:
            has_final_test = db.query(Attempt.id).filter_by(participant_id=participant.id, phase="final_test").first() is not None
            variant_number = max(1, min(4, round_number - (1 if has_final_test else 0)))
            expected_variant = f"retest_v{variant_number}"

    query = (
        db.query(Question)
        .filter(
            Question.term_id == term.id,
            Question.phase == phase,
            Question.is_active.is_(True),
        )
        .order_by(Question.variant_key)
    )
    candidates = query.all()
    if expected_variant:
        return next((question for question in candidates if question.variant_key == expected_variant), candidates[0] if candidates else None)
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
    participant = get_participant(db, participant_id)
    term = db.query(Term).filter_by(slug=term_slug).one_or_none()
    if not term or not term.is_active:
        raise HTTPException(status_code=404, detail="term not found")
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
    latest_open_turn = (
        db.query(TutorTurn)
        .filter_by(tutor_session_id=session.id, learner_response=None)
        .order_by(TutorTurn.turn_index.desc(), TutorTurn.created_at.desc())
        .first()
    )
    if latest_open_turn:
        return latest_open_turn
    position = _learning_position(db, session, term, participant)
    if position["learning_stage"] == "final_feedback":
        raise HTTPException(status_code=400, detail="learning session already completed")

    current_level = normalize_level(state.scaffolding_level)
    misconception_history = session_misconception_history(db, session.id)
    previous_learning_misconception = misconception_history[-1] if misconception_history else None
    effective_misconception = (previous_learning_misconception or {}).get("misconception_type") or state.primary_misconception
    effective_status = "unknown" if effective_misconception == "unknown" else ("misconception" if effective_misconception else state.current_status)
    effective_strategy = strategy_for(effective_misconception, effective_status, participant.group_condition)
    if participant.group_condition == "control":
        effective_strategy = "general_explanation"

    existing_turns = db.query(TutorTurn).filter_by(tutor_session_id=session.id).all()
    stage_turn_count = sum(
        1 for turn in existing_turns if _practice_meta(turn).get("learning_stage") == position["learning_stage"]
    )
    learning_variant_index = min(stage_turn_count + 1, 5)
    spec = _learning_question_spec(
        term.slug,
        position["learning_stage"],
        position["component_term"],
        learning_variant_index,
    )
    question_type = "control_learning_multi_select" if participant.group_condition == "control" else spec["question_type"]
    practice_question = {
        "body": spec["body"],
        "expected_answer": spec["expected_answer"],
        "question_type": question_type,
        "options": _public_learning_options(spec),
        "selection_mode": spec.get("selection_mode", "multiple"),
        "min_selections": spec.get("min_selections", 3),
        "max_selections": spec.get("max_selections", 3),
        "variant_key": spec["variant_key"],
        "learning_variant_index": learning_variant_index,
    }
    tutor_message = _previous_turn_prefix(previous_turn) + spec["material"]
    teaching_strategy = effective_strategy
    material_source = "ai"
    material_generation_ms = None
    common_payload = {
        "participant_id": participant.id,
        "group_condition": participant.group_condition,
        "term": {"slug": term.slug, "label": term.label, "description": term.description},
        "learning_stage": position["learning_stage"],
        "learning_stage_label": position["learning_stage_label"],
        "component_term": position["component_term"],
        "component_index": position["component_index"],
        "component_total": position["component_total"],
        "component_terms": _component_terms(term.slug, term.label),
        "fixed_practice_question": {
            "body": spec["body"],
            "expected_answer": spec["expected_answer"],
            "question_type": question_type,
            "options": _public_learning_options(spec),
            "selection_mode": practice_question.get("selection_mode"),
            "min_selections": practice_question.get("min_selections"),
            "max_selections": practice_question.get("max_selections"),
            "variant_key": spec["variant_key"],
        },
        "fixed_practice_question_items": _public_learning_options(spec),
        "rag_context": _rag_context(
            term.slug,
            term.label,
            term.description,
            position["learning_stage_label"],
            position["component_term"],
        ),
    }
    if participant.group_condition == "proposed":
        payload = {
            **common_payload,
            "learner_state": {
                "current_status": state.current_status,
                "primary_misconception": state.primary_misconception,
                "scaffolding_level": current_level,
                "teaching_strategy": effective_strategy,
                "recurrence_count": state.recurrence_count,
            },
            "previous_answer": previous_attempt.reason_text if previous_attempt else "",
            "previous_diagnosis_for_learner": state.state_summary,
            "previous_practice_question": _practice_question_text(previous_turn.practice_question_json if previous_turn else None),
            "previous_learner_response": previous_turn.learner_response if previous_turn else "",
            "previous_feedback_for_learner": previous_turn.ai_feedback if previous_turn else "",
            "previous_learning_misconception": previous_learning_misconception,
            "session_misconception_history": misconception_history,
            "misconception_scaffolding_guidance": _misconception_scaffolding_guidance(effective_misconception),
            "misconception_taxonomy": taxonomy_for_prompt(),
        }
    else:
        payload = common_payload
    started = perf_counter()
    result = await _ai_call(db, "generate_tutoring_turn", payload)
    material_generation_ms = int((perf_counter() - started) * 1000)
    tutor_message = result["tutor_message"]
    teaching_strategy = result["teaching_strategy"]

    turn = TutorTurn(
        tutor_session_id=session.id,
        turn_index=turn_count + 1,
        scaffolding_level=current_level,
        teaching_strategy=teaching_strategy,
        previous_teaching_strategy=state.previous_teaching_strategy,
        strategy_changed=False,
        tutor_message=tutor_message,
        learner_prompt=spec["body"],
        practice_question_json=_merge_stage_meta(practice_question, position),
        diagnosis_json={"material_source": material_source, "material_generation_ms": material_generation_ms},
        forbidden_help_given=False,
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
    learning_stage = meta.get("learning_stage") or "conceptual_change"
    variant_index = int((turn.practice_question_json or {}).get("learning_variant_index") or 1)
    component_index = int(meta.get("component_index") or 0)
    component_total = int(meta.get("component_total") or 1)
    component_term = meta.get("component_term")

    spec = _learning_question_spec(term.slug, learning_stage, component_term, variant_index)
    selected_options = _selected_learning_options(spec, payload.get("selected_option_ids"), payload.get("selected_option_id"), response)
    if spec.get("selection_mode") == "multiple":
        _validate_multi_select_labels({_option_label(option) for option in selected_options}, len(selected_options))
    result = _fixed_feedback_for_options(selected_options, spec)
    response = result.get("selected_option_body") or response

    is_sufficient = bool(result.get("is_sufficient"))
    learning_misconception_type = result.get("learning_misconception_type")
    if learning_misconception_type not in {"M1", "M3", "unknown", None}:
        learning_misconception_type = "unknown"
    learning_misconception_confidence = result.get("learning_misconception_confidence")
    learning_misconception_reason = result.get("learning_misconception_reason") or result.get("state_update_reason") or ""
    diagnosed_status = "stable_correct" if is_sufficient else ("unknown" if learning_misconception_type == "unknown" else "misconception")
    next_level = normalize_level(lower_level(state.scaffolding_level) if is_sufficient else raise_level(state.scaffolding_level))
    stage_completed = is_sufficient
    next_learning_stage = "final_feedback" if is_sufficient else _learning_stage_for_misconception(learning_misconception_type, diagnosed_status)
    session_completed = is_sufficient
    next_action = "move_next" if is_sufficient else "continue"

    selected_explanation_options = [
        option for option in selected_options if is_sufficient or not option.get("is_correct")
    ]
    selected_explanation_bodies = [option.get("body", "") for option in selected_explanation_options if option.get("body")]
    explanation_payload = {
        "participant_id": participant.id,
        "group_condition": participant.group_condition,
        "term": {"slug": term.slug, "label": term.label, "description": term.description},
        "learning_stage": learning_stage,
        "component_term": component_term,
        "question_body": spec["body"],
        "selected_option_body": " / ".join(selected_explanation_bodies),
        "selected_option_bodies": selected_explanation_bodies,
        "material": turn.tutor_message or "",
        "rag_context": _rag_context(
            term.slug,
            term.label,
            term.description,
            LEARNING_STAGE_LABELS.get(learning_stage, learning_stage),
            component_term,
        ),
    }
    if participant.group_condition == "proposed":
        explanation_payload.update(
            {
                "learner_state": {
                    "current_status": state.current_status,
                    "primary_misconception": state.primary_misconception,
                    "scaffolding_level": normalize_level(state.scaffolding_level),
                    "teaching_strategy": strategy_for(
                        learning_misconception_type,
                        diagnosed_status,
                        participant.group_condition,
                    ),
                    "recurrence_count": state.recurrence_count,
                },
                "learning_misconception_type": learning_misconception_type,
                "misconception_scaffolding_guidance": _misconception_scaffolding_guidance(learning_misconception_type),
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

    turn.learner_response = response
    turn.learner_confidence = None
    turn.question_shown_at = _naive_datetime(payload.get("question_shown_at"))
    turn.answered_at = _naive_datetime(payload.get("answered_at"))
    turn.response_time_sec = payload.get("response_time_sec")
    turn.next_scaffolding_level = next_level
    turn.ai_feedback = feedback_text
    turn.grading_json = {
        "is_sufficient": is_sufficient,
        "selected_option_id": selected_options[0]["option_id"] if selected_options else payload.get("selected_option_id"),
        "selected_option_ids": [option["option_id"] for option in selected_options],
        "selected_option_body": result.get("selected_option_body") or response,
        "learning_stage": learning_stage,
        "component_term": component_term,
        "component_index": component_index,
        "component_total": component_total,
        "item_results": [],
        "stage_completed": stage_completed,
        "next_learning_stage": next_learning_stage,
        "next_component_index": component_total if is_sufficient else component_index,
        "diagnosed_status": diagnosed_status,
        "learning_misconception_type": learning_misconception_type,
        "learning_misconception_confidence": learning_misconception_confidence,
        "learning_misconception_reason": learning_misconception_reason,
        "ai_next_action": result.get("next_action"),
        "response_time_sec": payload.get("response_time_sec"),
        "material_source": (turn.diagnosis_json or {}).get("material_source"),
        "material_generation_ms": (turn.diagnosis_json or {}).get("material_generation_ms"),
    }
    state.scaffolding_level = next_level
    state.stable_correct_count += 1 if is_sufficient else 0
    state.current_status = "stable_correct" if session_completed else diagnosed_status
    state.primary_misconception = None if is_sufficient else learning_misconception_type
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
        "next_component_index": component_total if is_sufficient else component_index,
        "learning_misconception_type": learning_misconception_type,
        "learning_misconception_confidence": learning_misconception_confidence,
        "learning_misconception_reason": learning_misconception_reason,
        "next_scaffolding_level": next_level,
        "turn_index": turn.turn_index,
        "max_turns": get_settings().max_turns_per_term,
        "item_results": [],
    }

async def score_phase(db: Session, participant_id: str, phase: str) -> dict[str, Any]:
    participant = get_participant(db, participant_id)
    if phase == "final_test" and participant.current_step != "final_test":
        raise HTTPException(status_code=409, detail=FINAL_TEST_NOT_AVAILABLE_DETAIL)
    attempts = db.query(Attempt).filter_by(participant_id=participant.id, phase=phase, is_correct=None).all()
    if not attempts:
        raise HTTPException(status_code=400, detail=f"{phase} attempts not found")
    for attempt in attempts:
        question = db.get(Question, attempt.question_id)
        option = _selected_option(db, attempt)
        options = _selected_options(db, attempt)
        payload = {
            "participant_id": participant.id,
            "group_condition": participant.group_condition,
            "question": {"id": question.id, "phase": phase, "body": question.body, "expected_answer": question.expected_answer, "expected_keywords": question.expected_keywords},
            "selected_option": None if not option else {"id": option.id, "body": option.body, "is_correct": option.is_correct, "initial_misconception_type": option.misconception_type},
            "selected_options": [
                {"id": item.id, "label": item.option_label, "body": item.body, "is_correct": item.is_correct, "initial_misconception_type": item.misconception_type}
                for item in options
            ],
            "free_text_answer": attempt.free_text_answer,
            "reason_text": attempt.reason_text,
        }
        if participant.group_condition == "proposed":
            payload["misconception_taxonomy"] = taxonomy_for_prompt()
        if "multi_select" in question.question_type:
            result = _fixed_attempt_result(options)
        elif phase in {"retest", "final_test"} and option:
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
            if previous and previous.misconception_type in {"M1", "M3"} and previous.misconception_type == attempt.misconception_type:
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
        state.current_status = "stable_correct" if attempt.is_correct else ("unknown" if attempt.misconception_type == "unknown" else "misconception")
        state.primary_misconception = None if attempt.is_correct else attempt.misconception_type
        state.last_attempt_id = attempt.id
    learning_target_slugs: list[str] = []
    next_url: str | None = None
    if phase == "retest":
        db.flush()
        learning_target_slugs = _reset_test_learning_targets(db, participant, attempts)
        if _is_mastery_test_batch(db, attempts):
            participant.current_step = "survey"
            next_url = _next_url(participant.current_step)
        else:
            participant.current_step = "learning_targets"
            next_url = f"/learning/{learning_target_slugs[0]}" if learning_target_slugs else _next_url(participant.current_step)
    elif phase == "l0_check":
        participant.current_step = "finish"
        participant.completed_at = now()
    elif phase == "final_test":
        learning_target_slugs = _reset_test_learning_targets(db, participant, attempts)
        if _is_mastery_test_batch(db, attempts):
            participant.current_step = "survey"
            next_url = _next_url(participant.current_step)
        else:
            participant.current_step = "learning_targets"
            next_url = f"/learning/{learning_target_slugs[0]}" if learning_target_slugs else _next_url(participant.current_step)
    db.commit()
    response: dict[str, Any] = {"status": "completed", "next_step": participant.current_step, "next_url": next_url or _next_url(participant.current_step)}
    if phase in {"retest", "final_test"}:
        response["learning_target_slugs"] = learning_target_slugs
    return response


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
    phase_order = {"l0_check": 0, "transfer": 1}
    return (2, phase_order.get(phase, 99), attempt_index)


def _attempt_sort_key(attempt: Attempt) -> tuple[int, int, int, str]:
    return (*_round_sort_key(_attempt_test_round(attempt), attempt.phase, attempt.attempt_index), attempt.created_at.isoformat())


def _test_rounds(attempts: list[Attempt]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, int], list[Attempt]] = {}
    for attempt in attempts:
        if attempt.phase not in {"pretest", "retest", "final_test", "l0_check"}:
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
        if attempt.phase in {"pretest", "retest", "final_test", "l0_check"}:
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
    sessions = db.query(TutorSession).filter_by(participant_id=participant_id).all()
    session_ids = [session.id for session in sessions]
    turns = db.query(TutorTurn).filter(TutorTurn.tutor_session_id.in_(session_ids or ["__none__"])).all()
    retest_count = max(
        (_round_number(_attempt_test_round(attempt)) or 0 for attempt in attempts if attempt.phase in {"retest", "final_test"}),
        default=0,
    )
    test_time = sum(attempt.response_time_sec or 0 for attempt in attempts if attempt.phase in {"pretest", "retest", "final_test", "l0_check"})
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
        "strategy_changed_count": sum(1 for turn in turns if turn.strategy_changed),
        "forbidden_help_count": sum(1 for turn in turns if turn.forbidden_help_given),
        "manual_review_count": sum(1 for attempt in attempts if attempt.requires_manual_review),
    }


def recalculate_evaluation(db: Session, participant_id: str) -> EvaluationSummary:
    participant = get_participant(db, participant_id)
    attempts = db.query(Attempt).filter_by(participant_id=participant.id).all()
    by_phase = {phase: [a for a in attempts if a.phase == phase] for phase in ["pretest", "retest", "l0_check", "final_test"]}
    final_items = by_phase["final_test"] or by_phase["l0_check"]
    final_score_source = "final_test" if by_phase["final_test"] else ("l0_check" if by_phase["l0_check"] else None)
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
        return bool(attempt.is_correct) if final_score_source == "retest_mastery" else bool(attempt.l0_success)

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
        l0_correct_rate=_rate(final_items, final_score_value),
        transfer_correct_rate=None,
        same_misconception_recurrence_rate=(len(same_rec) / len(initial_m)) if initial_m else None,
        m1_recurrence_rate=m_rate("M1"),
        m2_recurrence_rate=m_rate("M2"),
        m3_recurrence_rate=m_rate("M3"),
        m4_failure_rate=None,
        unknown_persistence_rate=None,
        learning_target_count=db.query(func.count(TermAssignment.id)).filter_by(participant_id=participant.id, is_learning_target=True).scalar() or 0,
        score_timeline_json={
            "rounds": _test_rounds(attempts),
            "final_test_skipped_after_retest_mastery": final_test_skipped,
            "final_score_source": final_score_source,
        },
        misconception_timeline_json=_misconception_timeline(attempts, _term_map(db)),
        learning_burden_json=_learning_burden(db, participant.id, attempts),
        condition_check_json=condition_check,
        completed=participant.completed_at is not None,
    )
    db.add(summary)
    db.commit()
    db.refresh(summary)
    return summary


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


def admin_summary(db: Session) -> dict[str, Any]:
    participants = db.query(Participant).all()
    terms = _term_map(db)
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
        def avg_final_delta() -> float | None:
            vals = []
            for summary in latest_summaries:
                rounds = (summary.score_timeline_json or {}).get("rounds") or []
                final_round = next((row for row in reversed(rounds) if row.get("phase") in {"final_test", "l0_check"}), None)
                if final_round and final_round.get("score_delta_from_pretest_pt") is not None:
                    vals.append(final_round["score_delta_from_pretest_pt"])
                elif (summary.score_timeline_json or {}).get("final_score_source") == "retest_mastery" and summary.pretest_score is not None and summary.l0_correct_rate is not None:
                    vals.append(round((summary.l0_correct_rate - summary.pretest_score) * 100, 6))
            return sum(vals) / len(vals) if vals else None
        rows.append(
            {
                "group_condition": group,
                "participant_count": len(group_participants),
                "same_misconception_recurrence_rate": avg("same_misconception_recurrence_rate"),
                "l0_correct_rate": avg("l0_correct_rate"),
                "avg_score_delta_from_pretest_pt": avg_final_delta(),
                "misconception_transition_summary": _group_misconception_transition_summary(group_participants, latest_summaries, terms),
            }
        )
    return {"groups": rows}


EXPORTS = {
    "participants": (Participant, ["id", "display_code", "group_condition", "assignment_method", "current_step", "started_at", "completed_at"]),
    "attempts": (Attempt, ["id", "participant_id", "term_id", "phase", "test_round", "question_id", "selected_option_id", "selected_option_ids", "reason_text", "free_text_answer", "response_time_sec", "question_shown_at", "answered_at", "question_body_snapshot", "option_order_snapshot", "is_correct", "score", "diagnosed_status", "misconception_type", "recurrence_flag", "l0_success", "requires_manual_review", "created_at"]),
    "learner_states": (LearnerState, ["participant_id", "term_id", "current_status", "primary_misconception", "scaffolding_level", "teaching_strategy", "stable_correct_count", "recurrence_count", "l0_success_count", "updated_at"]),
    "tutor_sessions": (TutorSession, ["id", "participant_id", "term_id", "session_index", "group_condition", "started_at", "ended_at"]),
    "tutor_turns": (TutorTurn, ["id", "tutor_session_id", "turn_index", "scaffolding_level", "teaching_strategy", "strategy_changed", "tutor_message", "learner_response", "ai_feedback", "next_scaffolding_level", "forbidden_help_given", "question_shown_at", "answered_at", "response_time_sec", "created_at"]),
    "recurrence_events": (RecurrenceEvent, ["id", "participant_id", "term_id", "previous_attempt_id", "current_attempt_id", "previous_misconception_type", "current_misconception_type", "is_same_type", "phase", "created_at"]),
    "ai_call_logs": (AICallLog, ["id", "provider", "fallback_provider", "purpose", "status", "error_code", "latency_ms", "created_at"]),
    "evaluation_summary": (EvaluationSummary, ["participant_id", "group_condition", "pretest_score", "retest_score", "l0_correct_rate", "same_misconception_recurrence_rate", "m1_recurrence_rate", "m2_recurrence_rate", "m3_recurrence_rate", "learning_target_count", "score_timeline_json", "misconception_timeline_json", "learning_burden_json", "condition_check_json", "completed", "created_at"]),
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
    selected_options = [options[option_id] for option_id in (attempt.selected_option_ids or []) if option_id in options]
    selected_option_body = _selected_option_label_text(selected_options) or (option.body if option else None)
    return {
        "attempt_id": attempt.id,
        "participant_id": attempt.participant_id,
        "display_code": participant.display_code if participant else None,
        "group_condition": participant.group_condition if participant else None,
        "phase": attempt.phase,
        "test_round": _attempt_test_round(attempt),
        "term_slug": term.slug if term else None,
        "term_label": term.label if term else None,
        "question_body": question.body if question else None,
        "selected_option_body": selected_option_body,
        "selected_option_ids": attempt.selected_option_ids,
        "question_body_snapshot": attempt.question_body_snapshot,
        "option_order_snapshot": attempt.option_order_snapshot,
        "response_time_sec": attempt.response_time_sec,
        "question_shown_at": _iso(attempt.question_shown_at),
        "answered_at": _iso(attempt.answered_at),
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
    practice_question = turn.practice_question_json or {}
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
        "question_body": practice_question.get("body"),
        "selected_option_body": grading.get("selected_option_body"),
        "learner_response": turn.learner_response,
        "is_sufficient": grading.get("is_sufficient"),
        "learning_misconception_type": grading.get("learning_misconception_type"),
        "ai_feedback": turn.ai_feedback,
        "practice_question": practice_question,
        "grading_json": turn.grading_json,
        "response_time_sec": turn.response_time_sec if turn.response_time_sec is not None else grading.get("response_time_sec"),
        "question_shown_at": _iso(turn.question_shown_at),
        "answered_at": _iso(turn.answered_at),
        "forbidden_help_given": turn.forbidden_help_given,
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
        "component_term": None,
        "component_index": None,
        "component_total": None,
        "turn_index": None,
        "is_sufficient": None,
        "teaching_strategy": None,
        "learner_response": attempt_row.get("selected_option_body") or attempt_row.get("free_text_answer") or attempt_row.get("reason_text"),
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
        "free_text_answer": None,
        "reason_text": None,
        "learner_response": turn_row.get("selected_option_body") or turn_row.get("learner_response"),
    }


def _answer_history_turn_rows(turn_row: dict[str, Any]) -> list[dict[str, Any]]:
    item_results = (turn_row.get("grading_json") or {}).get("item_results") or []
    if not item_results:
        return [_answer_history_turn_row(turn_row)]
    rows = []
    for index, item in enumerate(item_results):
        rows.append(
            {
                **turn_row,
                "answer_log_id": f"tutor_turn:{turn_row['tutor_turn_id']}:item:{index}",
                "source_type": "learning_turn",
                "source_id": turn_row["tutor_turn_id"],
                "phase": "learning",
                "is_correct": item.get("is_correct"),
                "misconception_type": item.get("learning_misconception_type"),
                "recurrence_flag": None,
                "question_body": item.get("question_body"),
                "question_body_snapshot": item.get("question_body"),
                "option_order_snapshot": next(
                    (practice_item.get("options") for practice_item in (turn_row.get("practice_question") or {}).get("items", []) if practice_item.get("component_term") == item.get("component_term")),
                    None,
                ),
                "free_text_answer": None,
                "reason_text": None,
                "learner_response": item.get("selected_option_body"),
                "selected_option_body": item.get("selected_option_body"),
                "is_sufficient": item.get("is_sufficient"),
                "learning_misconception_type": item.get("learning_misconception_type"),
                "component_term": item.get("component_term"),
                "component_index": index,
                "component_total": len(item_results),
            }
        )
    return rows


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
    recent_attempt_rows = [_attempt_log_row(row, participant_by_id, terms, questions, options) for row in attempts]
    recent_turn_rows = [
        _turn_log_row(row, sessions[row.tutor_session_id], participant_by_id.get(sessions[row.tutor_session_id].participant_id), terms.get(sessions[row.tutor_session_id].term_id))
        for row in recent_turns
        if row.tutor_session_id in sessions
    ]
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
                "group_condition": _ai_log_group_condition(row, participant_by_id),
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
                "retest_score": row.retest_score,
                "l0_correct_rate": row.l0_correct_rate,
                "same_misconception_recurrence_rate": row.same_misconception_recurrence_rate,
                "score_timeline": row.score_timeline_json,
                "misconception_timeline": row.misconception_timeline_json,
                "learning_burden": row.learning_burden_json,
                "condition_check": row.condition_check_json,
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
            "turns": [_turn_log_row(turn, session, participant, terms.get(session.term_id)) for turn in turns_by_session.get(session.id, [])],
        }
        for session in sessions
    ]
    turn_rows = [turn for session in tutor_sessions for turn in session["turns"]]
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
        "attempts": attempt_rows,
        "answer_history": _answer_history_rows(attempt_rows, turn_rows),
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
            "score_timeline": summary.score_timeline_json,
            "misconception_timeline": summary.misconception_timeline_json,
            "learning_burden": summary.learning_burden_json,
            "condition_check": summary.condition_check_json,
            "completed": summary.completed,
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
            writer.writerow({col: _csv_value(getattr(row, col)) if isinstance(getattr(row, col), (dict, list)) else getattr(row, col) for col in columns})
    db.add(ExportJob(export_name=name, file_path=str(path), status="success", row_count=len(rows)))
    db.commit()
    return path
