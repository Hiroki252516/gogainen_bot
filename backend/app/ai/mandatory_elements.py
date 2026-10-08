from __future__ import annotations

from typing import Any

from app.ai.material_structure import evidence_sections, normalize_evidence, validate_material_structure


MANDATORY_MISCONCEPTION_TYPES = ("M1", "M3", "unknown")

_REQUIREMENTS: dict[str, dict[str, str]] = {
    "M1": {
        "wrong_belief": "誤った単一命題を明示する。",
        "correct_belief": "その命題を置き換える正しい考えを示す。",
        "counterexample": "誤った考えでは説明できず、正しい考えを支持する反例を示す。",
        "reason": "反例がなぜ誤った考えを否定するのかを説明する。",
    },
    "M3": {
        "wrong_category": "対象を置いている誤った上位カテゴリーを示す。",
        "correct_category": "対象が属する正しいカテゴリーを示す。",
        "boundary_criterion": "誤カテゴリーと正カテゴリーを分ける境界基準を示す。",
        "contrast_example": "近いカテゴリーとの比較を示す。",
    },
    "unknown": {
        "definition": "対象用語の基礎定義を示す。",
        "components": "理解に必要な主要構成要素を示す。",
        "role": "対象用語の役割または目的を示す。",
        "decision_criterion": "最小限の判断基準を示す。",
        "positive_example": "正しい具体例を示す。",
        "non_example": "対象ではない例、または混同しやすい非例を示す。",
    },
}


def mandatory_element_requirements(misconception_type: str | None) -> dict[str, str]:
    """Return the research-operation fields required for an MVP type."""
    return dict(_REQUIREMENTS.get(misconception_type or "", {}))


def expected_mandatory_type(payload: dict[str, Any]) -> str | None:
    """Resolve the current MVP type without inferring a new misconception."""
    if payload.get("group_condition") != "proposed":
        return None

    # An explicitly supplied active type is authoritative, including an
    # unsupported value. Falling back from an explicit type to an older
    # learner-state diagnosis would apply the wrong mandatory schema.
    if "active_misconception_type" in payload:
        active_type = payload.get("active_misconception_type")
        return active_type if isinstance(active_type, str) and active_type in MANDATORY_MISCONCEPTION_TYPES else None

    if payload.get("learning_stage") == "enrichment":
        return "unknown"

    previous = payload.get("previous_learning_misconception") or {}
    learner_state = payload.get("learner_state") or {}
    for candidate in (
        previous.get("misconception_type"),
        learner_state.get("primary_misconception"),
    ):
        if candidate in MANDATORY_MISCONCEPTION_TYPES:
            return candidate
    return None


def mandatory_elements_schema(misconception_type: str | None = None) -> dict[str, Any]:
    """Return a strict-schema-compatible evidence object for one MVP type.

    The app-server's structured-output schema follows the strict JSON Schema
    rules: every key listed in ``properties`` must also be listed in
    ``required``.  The tutoring turn already knows the active type, so keeping
    only that type's fields makes the contract both strict and unambiguous.
    """
    selected_type = misconception_type if misconception_type in MANDATORY_MISCONCEPTION_TYPES else None
    fields = mandatory_element_requirements(selected_type)
    if not fields:
        fields = {
            field: description
            for field_group in _REQUIREMENTS.values()
            for field, description in field_group.items()
        }

    properties: dict[str, Any] = {
        "type": {
            "type": "string",
            "enum": [selected_type] if selected_type else list(MANDATORY_MISCONCEPTION_TYPES),
        },
    }
    properties.update({field: {"type": "string"} for field in fields})
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def validate_mandatory_elements(
    result: dict[str, Any],
    expected_type: str | None,
    term_label: str | None = None,
) -> dict[str, Any]:
    """Validate both the structured evidence and its presence in tutor_message."""
    requirements = mandatory_element_requirements(expected_type)
    if not requirements:
        return {
            "required": False,
            "valid": True,
            "expected_type": expected_type,
            "actual_type": None,
            "required_fields": [],
            "missing": [],
        }

    missing: list[str] = []
    elements = result.get("mandatory_elements")
    if not isinstance(elements, dict):
        missing.append("mandatory_elements:missing")
        elements = {}

    actual_type = elements.get("type")
    if actual_type != expected_type:
        missing.append(f"type:expected_{expected_type}_got_{actual_type or 'empty'}")

    message = result.get("tutor_message") or ""
    if not isinstance(message, str):
        message = ""
    missing.extend(validate_material_structure(result, term_label)["missing"])
    normalized_message = normalize_evidence(message)
    placements: dict[str, list[int]] = {}
    for field in requirements:
        value = elements.get(field)
        if not isinstance(value, str) or not value.strip():
            missing.append(f"{field}:empty")
            continue
        if normalize_evidence(value) not in normalized_message:
            missing.append(f"{field}:evidence_not_in_tutor_message")
            continue
        placements[field] = evidence_sections(message, value)
        if not placements[field]:
            missing.append(f"{field}:evidence_not_in_section")

    return {
        "required": True,
        "valid": not missing,
        "expected_type": expected_type,
        "actual_type": actual_type,
        "required_fields": list(requirements),
        "evidence_placements": placements,
        "missing": missing,
    }


def mock_mandatory_elements(
    term_label: str,
    description: str,
    misconception_type: str,
    target: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Create deterministic evidence spans for MockAIBackend tests only."""
    if misconception_type == "M1":
        return {
            "type": "M1",
            "wrong_belief": (target or {}).get("observed_claim") or f"{term_label}は、用語名だけで判断できる単純な情報である。",
            "correct_belief": (target or {}).get("corrected_claim") or f"{term_label}は、{description}",
            "counterexample": (target or {}).get("contrast_example") or f"{term_label}の名前に似た処理でも、同じ役割を持たない場合がある。",
            "reason": (target or {}).get("mechanism_explanation") or "この反例は、用語名だけで役割を決める考えでは処理の違いを説明できないことを示す。",
        }
    if misconception_type == "M3":
        return {
            "type": "M3",
            "wrong_category": (target or {}).get("wrong_category") or f"{term_label}を、関連するすべてのAI処理と同じ種類に分類する。",
            "correct_category": (target or {}).get("correct_category") or (target or {}).get("corrected_claim") or f"{term_label}は、{description}",
            "boundary_criterion": (target or {}).get("boundary_criterion") or "何を処理し、どの役割を担う仕組みかでカテゴリーを分ける。",
            "contrast_example": (target or {}).get("contrast_example") or f"{term_label}と名前が似ていても、役割や情報の流れが異なる処理は別カテゴリーである。",
        }
    return {
        "type": "unknown",
        "definition": f"{term_label}は、{description}",
        "components": f"{term_label}は、対象・役割・処理の流れに分けて確認する。",
        "role": f"{term_label}は、情報を適切に扱うための役割を担う。",
        "decision_criterion": "定義、構成要素、役割の3点が説明できるかを確認する。",
        "positive_example": f"{term_label}の構成要素が役割を分担して働く場面が該当する。",
        "non_example": f"{term_label}の名前が含まれていても、定義や役割を満たさない処理は該当しない。",
    }
