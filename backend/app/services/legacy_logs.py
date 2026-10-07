"""Read-only projection of retired columns and old multi-item answer history."""

from typing import Any

from app.models import Attempt, EvaluationSummary, LearnerState, TutorTurn


LEGACY_COLUMNS = {
    Attempt: ("selected_option_id", "free_text_answer", "reason_text", "confidence", "secondary_misconception_type", "l0_success", "transfer_success", "requires_manual_review"),
    LearnerState: ("secondary_misconception", "scaffolding_level", "previous_teaching_strategy", "l0_success_count", "transfer_success_count"),
    TutorTurn: ("scaffolding_level", "previous_teaching_strategy", "strategy_changed", "learner_confidence", "next_scaffolding_level", "forbidden_help_given"),
    EvaluationSummary: ("transfer_correct_rate", "m2_recurrence_rate", "m4_failure_rate", "unknown_persistence_rate"),
}


def legacy_fields(row: Any) -> dict[str, Any]:
    fields = {name: getattr(row, f"legacy_{name}") for name in LEGACY_COLUMNS.get(type(row), ())}
    if isinstance(row, EvaluationSummary):
        fields["l0_correct_rate"] = row.attainment_correct_rate
    return fields


def legacy_selected_option_body(attempt: Attempt, options: dict[str, Any]) -> str | None:
    option_id = attempt.legacy_selected_option_id
    for option in attempt.option_order_snapshot or []:
        if isinstance(option, dict) and (option.get("option_id") or option.get("id")) == option_id and isinstance(option.get("body"), str):
            return option.get("body")
    option = options.get(option_id or "")
    return option.body if option else None


def legacy_turn_answer_rows(turn_row: dict[str, Any]) -> list[dict[str, Any]]:
    items = (turn_row.get("grading_json") or {}).get("item_results") or []
    rows = []
    for index, item in enumerate(items):
        rows.append({
            **turn_row,
            "answer_log_id": f"tutor_turn:{turn_row['tutor_turn_id']}:item:{index}",
            "source_type": "learning_turn",
            "source_id": turn_row["tutor_turn_id"],
            "phase": "learning",
            "is_correct": item.get("is_correct"),
            "misconception_type": item.get("learning_misconception_type"),
            "question_body": item.get("question_body"),
            "question_body_snapshot": item.get("question_body"),
            "option_order_snapshot": next((value.get("options") for value in (turn_row.get("practice_question") or {}).get("items", []) if value.get("component_term") == item.get("component_term")), None),
            "learner_response": item.get("selected_option_body"),
            "selected_option_body": item.get("selected_option_body"),
            "is_sufficient": item.get("is_sufficient"),
            "learning_misconception_type": item.get("learning_misconception_type"),
            "legacy_fields": {**(turn_row.get("legacy_fields") or {}), "component_term": item.get("component_term"), "component_index": index, "component_total": len(items)},
        })
    return rows
