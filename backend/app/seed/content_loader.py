from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


CONTENT_PATH = Path(__file__).with_name("content") / "learning_content.yml"
ACTIVE_TERM_SLUGS = ("llm_knowledge", "multi_agent", "memory_process")
QUESTION_PHASES = ("pretest", "retest", "final_test")
LEARNING_STAGES = ("enrichment", "conceptual_change")


def _contains_langgraph(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_langgraph(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_contains_langgraph(item) for item in value)
    return "langgraph" in str(value).lower()


def _option_tuples(options: list[dict[str, Any]]) -> list[tuple[str, str, bool, str | None]]:
    return [
        (
            str(option["label"]),
            str(option["body"]),
            bool(option.get("is_correct")),
            option.get("misconception_type"),
        )
        for option in options
    ]


def _validate_option_set(name: str, options: Any) -> None:
    if not isinstance(options, list) or len(options) != 10:
        raise ValueError(f"{name} must contain exactly 10 options")
    labels = [option.get("label") for option in options]
    if labels != list("ABCDEFGHIJ"):
        raise ValueError(f"{name} labels must be A-J")
    correct = [option for option in options if option.get("is_correct")]
    if [option["label"] for option in correct] != ["A", "B", "C"]:
        raise ValueError(f"{name} must mark A-C as the only correct options")
    types = [option.get("misconception_type") for option in options]
    if types.count("M1") != 3 or types.count("M3") != 3 or types.count("unknown") != 1:
        raise ValueError(f"{name} must contain M1=3, M3=3, unknown=1")
    if any(option.get("misconception_type") not in {None, "M1", "M3", "unknown"} for option in options):
        raise ValueError(f"{name} contains an unsupported misconception type")
    if any(_contains_langgraph(option.get("body", "")) for option in options):
        raise ValueError(f"{name} must not mention LangGraph")


def _validate_teaching_targets(content: dict[str, Any]) -> None:
    targets = content.get("teaching_targets") or {}
    for term in content.get("terms") or []:
        slug = term["slug"]
        option_targets = targets.get(slug) or {}
        options = (term.get("questions") or {}).get("pretest", [{}])[0].get("options") or []
        for option in options:
            label = option.get("label")
            misconception_type = option.get("misconception_type")
            target = option_targets.get(label)
            if misconception_type in {"M1", "M3"}:
                if not isinstance(target, dict):
                    raise ValueError(f"teaching_targets.{slug}.{label} is required")
                required = {"corrected_claim", "mechanism_explanation", "contrast_example"}
                if misconception_type == "M3":
                    required |= {"wrong_category", "correct_category", "boundary_criterion"}
                if any(not str(target.get(field) or "").strip() for field in required):
                    raise ValueError(f"teaching_targets.{slug}.{label} is incomplete")
            elif target is not None:
                raise ValueError(f"teaching_targets.{slug}.{label} must not target {misconception_type}")


def _validate_variant(term_slug: str, phase: str, variant: Any) -> None:
    if not isinstance(variant, dict) or not variant.get("variant_key") or not variant.get("body"):
        raise ValueError(f"{term_slug}.{phase} contains an invalid variant")
    _validate_option_set(f"{term_slug}.{phase}.{variant['variant_key']}", variant.get("options"))
    if _contains_langgraph(variant.get("body", "")):
        raise ValueError(f"{term_slug}.{phase}.{variant['variant_key']} must not mention LangGraph")


def _validate_content(content: dict[str, Any]) -> None:
    if tuple(term.get("slug") for term in content.get("terms", [])) != ACTIVE_TERM_SLUGS:
        raise ValueError(f"active terms must be exactly {ACTIVE_TERM_SLUGS}")
    policy = content.get("selection_policy") or {}
    if policy.get("correct_labels") != ["A", "B", "C"] or policy.get("unknown_label") != "J":
        raise ValueError("selection policy must use A-C as correct and J as unknown")

    for name, options in (content.get("option_sets") or {}).items():
        _validate_option_set(f"option_sets.{name}", options)

    _validate_teaching_targets(content)

    for term in content["terms"]:
        slug = term["slug"]
        if not term.get("description") or not term.get("keywords") or not term.get("rag_sections"):
            raise ValueError(f"{slug} is missing metadata")
        questions = term.get("questions") or {}
        for phase in QUESTION_PHASES:
            variants = questions.get(phase) or []
            expected_count = 4 if phase == "retest" else 1
            if len(variants) != expected_count:
                raise ValueError(f"{slug}.{phase} must contain {expected_count} variant(s)")
            expected_keys = [
                f"{phase}_v{index}"
                for index in range(1, expected_count + 1)
            ]
            if [variant.get("variant_key") for variant in variants] != expected_keys:
                raise ValueError(f"{slug}.{phase} must use variant keys {expected_keys}")
            if len({variant.get("variant_key") for variant in variants}) != expected_count:
                raise ValueError(f"{slug}.{phase} has duplicate variant keys")
            for variant in variants:
                _validate_variant(slug, phase, variant)
        learning = term.get("learning") or {}
        for stage in LEARNING_STAGES:
            variants = (learning.get(stage) or {}).get("variants") or []
            if len(variants) != 5:
                raise ValueError(f"{slug}.learning.{stage} must contain 5 variants")
            expected_keys = [f"learning_{stage}_v{index}" for index in range(1, 6)]
            if [variant.get("variant_key") for variant in variants] != expected_keys:
                raise ValueError(f"{slug}.learning.{stage} must use variant keys {expected_keys}")
            if len({variant.get("variant_key") for variant in variants}) != 5:
                raise ValueError(f"{slug}.learning.{stage} has duplicate variant keys")
            for variant in variants:
                _validate_variant(slug, f"learning.{stage}", variant)
        if _contains_langgraph(term) or _contains_langgraph(term.get("rag_sections")):
            raise ValueError(f"{slug} must not mention LangGraph")


@lru_cache(maxsize=1)
def load_content() -> dict[str, Any]:
    with CONTENT_PATH.open("r", encoding="utf-8") as handle:
        content = yaml.safe_load(handle)
    if not isinstance(content, dict):
        raise ValueError("learning_content.yml must contain a mapping")
    _validate_content(content)
    return content


def content_term(term_slug: str) -> dict[str, Any]:
    return next(term for term in load_content()["terms"] if term["slug"] == term_slug)


def teaching_target_for_option(term_slug: str, option_label: str) -> dict[str, Any] | None:
    targets = (load_content().get("teaching_targets") or {}).get(term_slug) or {}
    target = targets.get(option_label)
    return deepcopy(target) if isinstance(target, dict) else None


def learning_question_spec(term_slug: str, learning_stage: str, variant_index: int = 1) -> dict[str, Any]:
    term = content_term(term_slug)
    stage = learning_stage if learning_stage in LEARNING_STAGES else "conceptual_change"
    stage_data = term["learning"][stage]
    variants = stage_data["variants"]
    index = min(max(variant_index, 1), len(variants)) - 1
    variant = dict(variants[index])
    variant["material"] = stage_data["material"]
    variant["options"] = [
        {**option, "option_id": option["label"]} for option in variant.get("options") or []
    ]
    variant["question_type"] = "learning_multi_select"
    variant["expected_answer"] = "A、B、Cをすべて選択し、それ以外を選ばない。"
    variant["selection_mode"] = "multiple"
    variant["min_selections"] = 3
    variant["max_selections"] = 3
    return variant


def seed_terms() -> list[dict[str, Any]]:
    terms: list[dict[str, Any]] = []
    for term in load_content()["terms"]:
        questions = term["questions"]
        normalized_questions: dict[str, Any] = {
            "pretest": {**questions["pretest"][0], "options": _option_tuples(questions["pretest"][0]["options"])},
            "retest": [
                {**variant, "options": _option_tuples(variant["options"])} for variant in questions["retest"]
            ],
            "final_test": {**questions["final_test"][0], "options": _option_tuples(questions["final_test"][0]["options"])},
            "l0": questions["l0"],
            "transfer": questions["transfer"],
        }
        terms.append({**term, "questions": normalized_questions})
    return terms
