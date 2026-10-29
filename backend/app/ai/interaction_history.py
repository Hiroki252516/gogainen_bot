from __future__ import annotations

import hashlib
import json
from typing import Any

from app.ai.mandatory_elements import expected_mandatory_type


INTERACTION_HISTORY_VERSION = "interaction-history-v1"
SHARED_QUESTION_ROUTE_VERSION = "shared-diagnosis-route-v1"
COMMON_INPUT_KEYS = ("term", "component_terms", "rag_context", "interaction_history", "learning_scope")
HISTORY_RECORD_KEYS = (
    "source_type", "phase", "test_round", "session_index", "turn_index",
    "question_body", "is_correct", "question_shown_at", "answered_at", "response_time_sec",
)
HISTORY_TEXT_KEYS = {"source_type", "phase", "test_round", "question_body", "question_shown_at", "answered_at"}
PROPOSED_TUTORING_KEYS = (
    "learning_stage", "learning_stage_label", "pretest_target", "pretest_targets", "learner_state",
    "previous_diagnosis_for_learner", "previous_learning_misconception", "session_misconception_history",
    "misconception_teaching_guidance", "misconception_taxonomy", "active_misconception_type",
    "mandatory_teaching_elements", "diagnostic_evidence", "mandatory_element_retry",
)
FEEDBACK_INPUT_KEYS = ("question_body", "selected_option_body", "selected_option_bodies", "material")
PROPOSED_FEEDBACK_KEYS = (
    "learning_stage", "learner_state", "learning_misconception_type",
    "misconception_teaching_guidance", "misconception_taxonomy", "session_misconception_history",
)


def project_interaction_history(value: Any) -> list[dict[str, Any]]:
    """Copy observed answers only; never forward diagnostic fields nested in a history."""
    if not isinstance(value, list):
        return []
    records = []
    for row in value:
        if not isinstance(row, dict):
            continue
        record = {}
        for key in HISTORY_RECORD_KEYS:
            if key not in row:
                continue
            item = row[key]
            if key in HISTORY_TEXT_KEYS:
                valid = item is None or isinstance(item, str)
            elif key == "is_correct":
                valid = isinstance(item, bool)
            else:
                valid = item is None or (isinstance(item, (int, float)) and not isinstance(item, bool))
            if valid:
                record[key] = item
        options = row.get("selected_options")
        record["selected_options"] = [
            {key: option[key] for key in ("label", "body") if isinstance(option.get(key), str)}
            for option in options if isinstance(option, dict)
        ] if isinstance(options, list) else []
        records.append(record)
    return records


def project_model_payload(payload: dict[str, Any], *, proposed: bool, feedback: bool = False) -> dict[str, Any]:
    result = {key: payload[key] for key in COMMON_INPUT_KEYS if key in payload}
    if "learning_scope" in result:
        scope = result["learning_scope"] if isinstance(result["learning_scope"], dict) else {}
        topics = scope.get("topics")
        errors = scope.get("selected_errors")
        result["learning_scope"] = {"topics": [text for text in topics if isinstance(text, str)] if isinstance(topics, list) else [],
                                    "selected_errors": [{key: row[key] for key in ("label", "body") if isinstance(row.get(key), str)} for row in errors if isinstance(row, dict)] if isinstance(errors, list) else []}
    if payload.get("explanation_level") == "beginner":
        result["explanation_level"] = "beginner"
    result["interaction_history"] = project_interaction_history(payload.get("interaction_history"))
    if isinstance(result.get("term"), dict):
        result["term"] = {key: result["term"][key] for key in ("slug", "label", "description") if key in result["term"] and (result["term"][key] is None or isinstance(result["term"][key], str))}
    if feedback:
        result.update({key: payload[key] for key in FEEDBACK_INPUT_KEYS if key in payload})
    if proposed:
        keys = PROPOSED_FEEDBACK_KEYS if feedback else PROPOSED_TUTORING_KEYS
        result.update({key: payload[key] for key in keys if key in payload})
        if isinstance(result.get("learner_state"), dict):
            result["learner_state"] = {
                key: value for key, value in result["learner_state"].items()
                if key in {"current_status", "primary_misconception", "teaching_strategy", "recurrence_count"}
            }
        if not feedback and expected_mandatory_type({**payload, "group_condition": "proposed"}) == "unknown":
            result["pretest_target"] = None
            result["pretest_targets"] = []
            result["diagnostic_evidence"] = {**(result.get("diagnostic_evidence") or {}), "pretest_targets": []}
    return result


def interaction_history_audit(payload: dict[str, Any]) -> dict[str, Any]:
    history = project_interaction_history(payload.get("interaction_history"))
    encoded = json.dumps(history, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"version": INTERACTION_HISTORY_VERSION, "record_count": len(history), "sha256": hashlib.sha256(encoded).hexdigest()}
