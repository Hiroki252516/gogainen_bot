from __future__ import annotations

import re
from typing import Any


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

_HEADINGS: dict[str, dict[str, str]] = {
    "M1": {
        "wrong_belief": "誤った考え",
        "correct_belief": "正しい考え",
        "counterexample": "反例",
        "reason": "誤りの理由",
    },
    "M3": {
        "wrong_category": "誤カテゴリー",
        "correct_category": "正カテゴリー",
        "boundary_criterion": "境界基準",
        "contrast_example": "近いカテゴリーとの比較",
    },
    "unknown": {
        "definition": "定義",
        "components": "構成要素",
        "role": "役割",
        "decision_criterion": "判断基準",
        "positive_example": "正例",
        "non_example": "非例",
    },
}

_GENERIC_HEADINGS = ("要点", "具体例", "注意点")


def mandatory_element_requirements(misconception_type: str | None) -> dict[str, str]:
    """Return the research-operation fields required for an MVP type."""
    return dict(_REQUIREMENTS.get(misconception_type or "", {}))


def mandatory_element_headings(misconception_type: str | None) -> dict[str, str]:
    """Return the learner-facing section heading for each required field."""
    return dict(_HEADINGS.get(misconception_type or "", {}))


def expected_mandatory_type(payload: dict[str, Any]) -> str | None:
    """Resolve the current MVP type without inferring a new misconception."""
    if payload.get("group_condition") != "proposed":
        return None

    active_type = payload.get("active_misconception_type")
    if active_type in MANDATORY_MISCONCEPTION_TYPES:
        return active_type

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


def mandatory_element_prompt(misconception_type: str | None) -> str:
    requirements = mandatory_element_requirements(misconception_type)
    headings = mandatory_element_headings(misconception_type)
    if not requirements:
        return ""
    lines = [
        f"現在の必須教授要素タイプは {misconception_type}。次の見出しをこの順序で教材本文に使う:",
    ]
    lines.extend(
        f"- {field} / ### {headings[field]}: {description}"
        for field, description in requirements.items()
    )
    lines.append("## 用語名の直後に、上記の ### 見出しを順番どおりに置く。")
    lines.append("M1/M3/unknownでは「### 要点」「### 具体例」「### 注意点」を使わない。")
    lines.append("mandatory_elements は type と上記フィールドを直下に持つオブジェクトにし、不要なフィールドや入れ子を追加しない。")
    lines.append("mandatory_elements の各値は、教材本文からそのまま抜き出した短い証拠文にする。")
    lines.append("各証拠文は、対応する見出しのセクション内に置く。")
    lines.append("mandatory_elements は研究ログ用であり、学習者向け本文に内部ラベルを表示しない。")
    return "\n".join(lines)


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
    if term_label and f"## {term_label}" not in message:
        missing.append("tutor_message:term_heading_missing")
    headings = mandatory_element_headings(expected_type)
    heading_positions: list[int] = []
    for heading in headings.values():
        marker = f"### {heading}"
        position = message.find(marker)
        if position < 0:
            missing.append(f"tutor_message:heading_missing:{marker}")
        else:
            heading_positions.append(position)
    if heading_positions != sorted(heading_positions):
        missing.append("tutor_message:heading_order_invalid")
    for heading in _GENERIC_HEADINGS:
        if re.search(rf"(?m)^###\s+{re.escape(heading)}\s*$", message):
            missing.append(f"tutor_message:generic_heading_forbidden:### {heading}")
    if re.search(r"\bM[1-4]\b", message):
        missing.append("tutor_message:internal_label_exposed")

    normalized_message = _normalize_evidence(message)
    for field, value_heading in headings.items():
        value = elements.get(field)
        if not isinstance(value, str) or not value.strip():
            missing.append(f"{field}:empty")
            continue
        if _normalize_evidence(value) not in normalized_message:
            missing.append(f"{field}:evidence_not_in_tutor_message")
            continue
        section = _heading_section(message, value_heading, tuple(headings.values()))
        if section and _normalize_evidence(value) not in _normalize_evidence(section):
            missing.append(f"{field}:evidence_not_in_section")

    return {
        "required": True,
        "valid": not missing,
        "expected_type": expected_type,
        "actual_type": actual_type,
        "required_fields": list(requirements),
        "missing": missing,
    }


def mock_mandatory_elements(term_label: str, description: str, misconception_type: str) -> dict[str, str]:
    """Create deterministic evidence spans for MockAIBackend tests only."""
    if misconception_type == "M1":
        return {
            "type": "M1",
            "wrong_belief": f"{term_label}は、用語名だけで判断できる単純な情報である。",
            "correct_belief": f"{term_label}は、{description}",
            "counterexample": f"{term_label}の名前に似た処理でも、同じ役割を持たない場合がある。",
            "reason": "この反例は、用語名だけで役割を決める考えでは処理の違いを説明できないことを示す。",
        }
    if misconception_type == "M3":
        return {
            "type": "M3",
            "wrong_category": f"{term_label}を、関連するすべてのAI処理と同じ種類に分類する。",
            "correct_category": f"{term_label}は、{description}",
            "boundary_criterion": "何を処理し、どの役割を担う仕組みかでカテゴリーを分ける。",
            "contrast_example": f"{term_label}と名前が似ていても、役割や情報の流れが異なる処理は別カテゴリーである。",
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


def _heading_section(message: str, heading: str, headings: tuple[str, ...]) -> str:
    marker = f"### {heading}"
    start = message.find(marker)
    if start < 0:
        return ""
    content_start = start + len(marker)
    following = [
        message.find(f"### {candidate}", content_start)
        for candidate in headings
        if candidate != heading and message.find(f"### {candidate}", content_start) >= 0
    ]
    content_end = min(following) if following else len(message)
    return message[content_start:content_end]


def _normalize_evidence(value: str) -> str:
    return re.sub(r"[\s*_`#>\[\]]+", "", value or "")
