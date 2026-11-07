from __future__ import annotations

from pathlib import Path
from string import Formatter
from typing import Any

import yaml


PROMPT_TEXT_PATH = Path(__file__).parent / "prompts" / "learning_material.yml"
MISCONCEPTION_TYPE_CODES = ("M1", "M3", "unknown")


def _required_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Prompt text section {name!r} must be a mapping")
    return value


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"Prompt text {name!r} must be a non-empty string")
    return value


def _required_text_list(value: Any, name: str, *, expected_length: int | None = None) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"Prompt text {name!r} must be a non-empty list of non-empty strings")
    if expected_length is not None and len(value) != expected_length:
        raise ValueError(f"Prompt text {name!r} must contain {expected_length} items")
    return value


def _validate_research_config(root: dict[str, Any]) -> None:
    research = _required_mapping(root.get("research_config"), "research_config")

    taxonomy = _required_mapping(
        research.get("misconception_taxonomy"), "research_config.misconception_taxonomy"
    )
    _required_text(taxonomy.get("version"), "research_config.misconception_taxonomy.version")
    taxonomy_types = _required_mapping(
        taxonomy.get("types"), "research_config.misconception_taxonomy.types"
    )
    if set(taxonomy_types) != set(MISCONCEPTION_TYPE_CODES):
        raise ValueError("research_config.misconception_taxonomy.types must define M1, M3, and unknown")
    for type_code in MISCONCEPTION_TYPE_CODES:
        name = f"research_config.misconception_taxonomy.types.{type_code}"
        definition = _required_mapping(taxonomy_types[type_code], name)
        for key in ("label", "definition", "learning_outcome", "research_basis"):
            _required_text(definition.get(key), f"{name}.{key}")
        for key in ("diagnostic_cues", "teaching_guidelines", "avoid"):
            _required_text_list(definition.get(key), f"{name}.{key}")

    mandatory = _required_mapping(research.get("mandatory_elements"), "research_config.mandatory_elements")
    if set(mandatory) != set(taxonomy_types):
        raise ValueError("research_config.mandatory_elements must define the same types as the taxonomy")
    for type_code in MISCONCEPTION_TYPE_CODES:
        name = f"research_config.mandatory_elements.{type_code}"
        fields = _required_mapping(mandatory[type_code], name)
        if not fields:
            raise ValueError(f"Prompt text section {name!r} must not be empty")
        for field, description in fields.items():
            _required_text(description, f"{name}.{field}")

    strategies = _required_mapping(research.get("teaching_strategies"), "research_config.teaching_strategies")
    _required_text(strategies.get("control"), "research_config.teaching_strategies.control")
    proposed = _required_mapping(strategies.get("proposed"), "research_config.teaching_strategies.proposed")
    by_type = _required_mapping(proposed.get("by_type"), "research_config.teaching_strategies.proposed.by_type")
    if set(by_type) != set(taxonomy_types):
        raise ValueError("research_config.teaching_strategies.proposed.by_type must define the taxonomy types")
    for type_code, value in by_type.items():
        _required_text(value, f"research_config.teaching_strategies.proposed.by_type.{type_code}")
    by_status = _required_mapping(
        proposed.get("by_status"), "research_config.teaching_strategies.proposed.by_status"
    )
    _required_text(by_status.get("unknown"), "research_config.teaching_strategies.proposed.by_status.unknown")


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
    glossary_rules = _required_text_list(tutoring.get("glossary_rules"), "tutoring.glossary_rules", expected_length=3)
    if any(field for rule in glossary_rules for _, field, _, _ in Formatter().parse(rule)):
        raise ValueError("Prompt text tutoring.glossary_rules must not contain template fields")
    _required_text(tutoring.get("validation_retry_prefix"), "tutoring.validation_retry_prefix")
    _required_text(tutoring.get("learning_scope_rule"), "tutoring.learning_scope_rule")
    group_rules = _required_mapping(tutoring.get("group_rules"), "tutoring.group_rules")
    if "control" in group_rules:
        raise ValueError("Prompt text section tutoring.group_rules.control is not supported")
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
    mandatory_rules = _required_mapping(tutoring.get("mandatory_element_rules"), "tutoring.mandatory_element_rules")
    _required_text(mandatory_rules.get("section_grouping"), "tutoring.mandatory_element_rules.section_grouping")
    _required_text_list(mandatory_rules.get("lines"), "tutoring.mandatory_element_rules.lines", expected_length=4)

    _validate_research_config(root)
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
