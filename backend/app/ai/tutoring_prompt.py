from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from app.ai.mandatory_elements import mandatory_element_requirements
from app.ai.prompt_config import (
    PROMPT_TEXT,
    PROMPT_TEXT_PATH as PROMPT_TEXT_PATH,
    _validate_prompt_text as _validate_prompt_text,
)
from app.ai.teaching_contract import material_length_contract


def mandatory_element_prompt(misconception_type: str | None) -> str:
    """Render the type-specific teaching instruction for教材生成."""
    requirements = mandatory_element_requirements(misconception_type)
    if not requirements:
        return ""
    rules = PROMPT_TEXT["tutoring"]
    lines = [
        rules["templates"]["mandatory_element_intro"].format(misconception_type=misconception_type),
    ]
    lines.extend(
        f"- {field}: {description}"
        for field, description in requirements.items()
    )
    lines.append(rules["mandatory_element_rules"]["section_grouping"])
    lines.extend(rules["mandatory_element_rules"]["lines"])
    return "\n".join(lines)


def compose_structured_prompt(
    purpose: str,
    payload: dict[str, Any],
    rules: Sequence[str],
) -> str:
    """Compose the common text envelope used for structured app-server calls."""
    structured_text = PROMPT_TEXT["structured"]
    prompt_parts = [
        f"{structured_text['purpose_prefix']}{purpose}",
        "",
        *structured_text["output_rules"],
        "",
        structured_text["additional_rules_heading"],
        *[f"- {rule}" for rule in rules],
    ]
    if payload.get("misconception_taxonomy"):
        prompt_parts.extend(
            [
                "",
                structured_text["taxonomy_intro"],
                json.dumps(payload["misconception_taxonomy"], ensure_ascii=False, indent=2),
            ]
        )
    prompt_payload = remove_routing_metadata(payload)
    prompt_parts.extend(["", structured_text["input_heading"], json.dumps(prompt_payload, ensure_ascii=False, indent=2)])
    return "\n".join(prompt_parts)


def build_tutoring_prompt(
    payload: dict[str, Any],
    *,
    retry_context: dict[str, Any] | None = None,
    group: str,
    expected_type: str | None,
    term_label: str,
    teaching_strategies: Sequence[str],
) -> str:
    """Build the complete教材生成 prompt in one auditable place.

    The input payload has already been allowlisted by the caller.  This builder
    owns only the textual instruction order; output schemas and local
    validation remain separate contracts.
    """
    if group not in {"control", "proposed"}:
        raise ValueError(f"Unsupported tutoring group: {group!r}")

    length_contract = material_length_contract()
    target_characters = length_contract["target_character_count"]
    prompt_text = PROMPT_TEXT["tutoring"]
    templates = prompt_text["templates"]
    common = prompt_text["common_rules"]
    rules = [
        common["opening"],
        templates["term_topic"].format(term_label=term_label),
        *common["context"],
        templates["material_length"].format(
            target_characters=target_characters,
        ),
        common["formatting"],
        common["heading"].format(term_label=term_label),
        common["heading_flexibility"],
        common["learner_visible_privacy"],
    ]
    if payload.get("glossary_reference"):
        glossary_rules = [*prompt_text["glossary_rules"]]
        rules.extend(glossary_rules)

    # ``retry_context`` is server-side generation metadata; only validation
    # errors selected below may contribute a retry instruction.
    retry_source = retry_context or payload
    if expected_type:
        expected_rules = prompt_text["expected_type_rules"]
        rules.extend(expected_rules["common"])
        if expected_type in {"M1", "M3"}:
            rules.extend(expected_rules["m1_m3"])
        else:
            rules.extend(expected_rules["unknown"])

    if expected_type:
        rules.append(mandatory_element_prompt(expected_type))
    validation_retry = retry_source.get("mandatory_element_retry")
    if isinstance(validation_retry, dict):
        retry_errors = validation_retry.get("missing", [])
        if group == "control":
            retry_errors = [error for error in retry_errors if isinstance(error, str) and (
                error.startswith("tutor_message:") or error == "teaching_strategy.mismatch"
            )]
        if retry_errors:
            rules.append(prompt_text["validation_retry_prefix"] + json.dumps(retry_errors, ensure_ascii=False))

    if payload.get("learning_scope"):
        rules.append(prompt_text["learning_scope_rule"])
    if group != "control":
        rules.extend(prompt_text["group_rules"]["proposed"])
        rules.append(templates["teaching_strategy"].format(strategies=", ".join(teaching_strategies)))

    return compose_structured_prompt("tutoring_turn", payload, rules)


def remove_routing_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: remove_routing_metadata(item)
            for key, item in value.items()
            if key not in {"participant_id", "group_condition", "participant_code"}
        }
    if isinstance(value, list):
        return [remove_routing_metadata(item) for item in value]
    return value
