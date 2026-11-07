from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from string import Formatter
from typing import Any

import yaml

from app.ai.mandatory_elements import mandatory_element_requirements
from app.ai.teaching_contract import material_length_contract


PROMPT_TEXT_PATH = Path(__file__).parent / "prompts" / "learning_material.yml"


def _required_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Prompt text section {name!r} must be a mapping")
    return value


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"Prompt text {name!r} must be a non-empty string")
    return value


def _required_text_list(value: Any, name: str, *, expected_length: int | None = None) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"Prompt text {name!r} must be a list of non-empty strings")
    if expected_length is not None and len(value) != expected_length:
        raise ValueError(f"Prompt text {name!r} must contain {expected_length} items")
    return value


def _validate_prompt_text(raw: Any) -> dict[str, Any]:
    root = _required_mapping(raw, "root")
    structured = _required_mapping(root.get("structured"), "structured")
    for key in ("purpose_prefix", "taxonomy_intro", "additional_rules_heading", "input_heading"):
        _required_text(structured.get(key), f"structured.{key}")
    _required_text_list(structured.get("output_rules"), "structured.output_rules", expected_length=3)

    tutoring = _required_mapping(root.get("tutoring"), "tutoring")
    common = _required_mapping(tutoring.get("common_rules"), "tutoring.common_rules")
    _required_text(common.get("opening"), "tutoring.common_rules.opening")
    _required_text_list(common.get("context"), "tutoring.common_rules.context", expected_length=6)
    for key in ("formatting", "heading", "heading_flexibility", "learner_visible_privacy"):
        _required_text(common.get(key), f"tutoring.common_rules.{key}")
    if {field for _, field, _, _ in Formatter().parse(common["heading"]) if field} != {"term_label"}:
        raise ValueError("Prompt text template tutoring.common_rules.heading has invalid fields")
    _required_text_list(tutoring.get("glossary_rules"), "tutoring.glossary_rules", expected_length=3)
    _required_text(tutoring.get("validation_retry_prefix"), "tutoring.validation_retry_prefix")
    _required_text(tutoring.get("learning_scope_rule"), "tutoring.learning_scope_rule")
    group_rules = _required_mapping(tutoring.get("group_rules"), "tutoring.group_rules")
    _required_text_list(group_rules.get("control"), "tutoring.group_rules.control", expected_length=3)
    _required_text_list(group_rules.get("proposed"), "tutoring.group_rules.proposed", expected_length=7)

    templates = _required_mapping(tutoring.get("templates"), "tutoring.templates")
    template_fields = {
        "term_topic": {"term_label"},
        "material_length": {"target_characters"},
        "mandatory_element_intro": {"misconception_type"},
        "teaching_strategy": {"strategies"},
    }
    for key, expected_fields in template_fields.items():
        template = _required_text(templates.get(key), f"tutoring.templates.{key}")
        fields = {field for _, field, _, _ in Formatter().parse(template) if field}
        if fields != expected_fields:
            raise ValueError(f"Prompt text template tutoring.templates.{key!s} has invalid fields")

    expected = _required_mapping(tutoring.get("expected_type_rules"), "tutoring.expected_type_rules")
    _required_text_list(expected.get("common"), "tutoring.expected_type_rules.common", expected_length=1)
    _required_text_list(expected.get("m1_m3"), "tutoring.expected_type_rules.m1_m3", expected_length=4)
    _required_text_list(expected.get("unknown"), "tutoring.expected_type_rules.unknown", expected_length=3)
    mandatory = _required_mapping(tutoring.get("mandatory_element_rules"), "tutoring.mandatory_element_rules")
    _required_text(mandatory.get("section_grouping"), "tutoring.mandatory_element_rules.section_grouping")
    _required_text_list(mandatory.get("lines"), "tutoring.mandatory_element_rules.lines", expected_length=4)
    return root


def _load_prompt_text() -> dict[str, Any]:
    try:
        raw = yaml.safe_load(PROMPT_TEXT_PATH.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise RuntimeError(f"Unable to load tutoring prompt text from {PROMPT_TEXT_PATH}") from exc
    try:
        return _validate_prompt_text(raw)
    except ValueError as exc:
        raise RuntimeError(f"Invalid tutoring prompt text in {PROMPT_TEXT_PATH}: {exc}") from exc


PROMPT_TEXT = _load_prompt_text()


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
    if group == "control":
        rules.extend(prompt_text["group_rules"]["control"])
    else:
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
