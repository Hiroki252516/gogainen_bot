from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


CONTENT_PATH = Path(__file__).with_name("content") / "learning_content.yml"
LEARNING_V2_CONTENT_PATH = Path(__file__).with_name("content") / "learning_questions_v2.yml"
ACTIVE_TERM_SLUGS = ("llm_knowledge", "multi_agent", "memory_process")
QUESTION_PHASES = ("pretest", "retest", "final_test")
LEARNING_STAGES = ("enrichment", "conceptual_change")
LEGACY_LEARNING_CONTENT_VERSION = 1
CURRENT_LEARNING_CONTENT_VERSION = 2
LEARNING_OPTION_ROLES = ("correct", "M1", "M3")
LEARNING_SCENARIO_TYPES = ("application", "prediction", "comparison", "boundary", "diagnosis")
UNKNOWN_OPTION = {"label": "J", "body": "わからない。", "is_correct": False, "misconception_type": "unknown"}


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
        pretest_variants = (term.get("questions") or {}).get("pretest") or []
        first_pretest = (
            pretest_variants[0]
            if isinstance(pretest_variants, list) and pretest_variants and isinstance(pretest_variants[0], dict)
            else {}
        )
        options = first_pretest.get("options") or []
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


def _v2_options(variant: dict[str, Any], rotation: int) -> list[dict[str, Any]]:
    choices = variant["choices"]
    options = []
    role_slots = ("correct", "correct", "correct", "M1", "M1", "M1", "M3", "M3", "M3")
    for label_index, label in enumerate("ABCDEFGHI"):
        slot = (label_index - rotation) % 9
        role = role_slots[slot]
        role_index = slot % 3
        options.append(
            {
                "label": label,
                "body": choices[role][role_index],
                "is_correct": role == "correct",
                "misconception_type": None if role == "correct" else role,
            }
        )
    options.append(dict(UNKNOWN_OPTION))
    return options


def _validate_v2_content(content: dict[str, Any], legacy_content: dict[str, Any]) -> None:
    if content.get("version") != CURRENT_LEARNING_CONTENT_VERSION:
        raise ValueError("learning_questions_v2.yml must have version 2")
    terms = content.get("terms") or {}
    if tuple(terms) != ACTIVE_TERM_SLUGS:
        raise ValueError(f"learning v2 terms must be exactly {ACTIVE_TERM_SLUGS}")

    legacy_options = {
        option["body"]
        for options in (legacy_content.get("option_sets") or {}).values()
        for option in options
    }
    legacy_bodies = {
        variant["body"]
        for term in legacy_content["terms"]
        for phase in QUESTION_PHASES
        for variant in (term.get("questions") or {}).get(phase, [])
    }
    role_counts = {label: {role: 0 for role in LEARNING_OPTION_ROLES} for label in "ABCDEFGHI"}
    variant_count = 0
    rotation = 0

    for term_slug in ACTIVE_TERM_SLUGS:
        stage_data = terms.get(term_slug) or {}
        if tuple(stage_data) != LEARNING_STAGES:
            raise ValueError(f"learning v2 stages for {term_slug} must be {LEARNING_STAGES}")
        for stage in LEARNING_STAGES:
            variants = (stage_data.get(stage) or {}).get("variants") or []
            if len(variants) != 5:
                raise ValueError(f"{term_slug}.{stage} must contain five v2 variants")
            expected_keys = [f"learning_{stage}_v{index}" for index in range(1, 6)]
            if [variant.get("variant_key") for variant in variants] != expected_keys:
                raise ValueError(f"{term_slug}.{stage} must use variant keys {expected_keys}")
            if [variant.get("scenario_type") for variant in variants] != list(LEARNING_SCENARIO_TYPES):
                raise ValueError(f"{term_slug}.{stage} must cover each scenario type once in order")

            for variant in variants:
                if not str(variant.get("scenario") or "").strip() or not str(variant.get("task") or "").strip():
                    raise ValueError(f"{term_slug}.{stage}.{variant.get('variant_key')} needs scenario and task")
                choices = variant.get("choices") or {}
                if tuple(choices) != LEARNING_OPTION_ROLES:
                    raise ValueError(f"{term_slug}.{stage}.{variant['variant_key']} must define correct, M1, and M3 choices")
                all_choice_bodies = []
                for role in LEARNING_OPTION_ROLES:
                    texts = choices.get(role)
                    if not isinstance(texts, list) or len(texts) != 3 or any(not str(text).strip() for text in texts):
                        raise ValueError(f"{term_slug}.{stage}.{variant['variant_key']} needs three nonempty {role} choices")
                    all_choice_bodies.extend(str(text).strip() for text in texts)
                lengths = [len(text) for text in all_choice_bodies]
                if min(lengths) < 20 or max(lengths) > min(lengths) * 1.8 or max(lengths) - min(lengths) > 32:
                    raise ValueError(f"{term_slug}.{stage}.{variant['variant_key']} has a conspicuous option-length spread")
                if len(set(all_choice_bodies)) != 9:
                    raise ValueError(f"{term_slug}.{stage}.{variant['variant_key']} has duplicate choices")
                if any(body in legacy_options or body in legacy_bodies for body in all_choice_bodies):
                    raise ValueError(f"{term_slug}.{stage}.{variant['variant_key']} copies fixed test wording")
                if _contains_langgraph(variant):
                    raise ValueError(f"{term_slug}.{stage}.{variant['variant_key']} must not mention LangGraph")

                for label_index, label in enumerate("ABCDEFGHI"):
                    slot = (label_index - rotation) % 9
                    role = LEARNING_OPTION_ROLES[slot // 3]
                    role_counts[label][role] += 1
                rotation = (rotation + 3) % 9
                variant_count += 1

    if variant_count != 30:
        raise ValueError("learning v2 bank must contain exactly 30 variants")
    if any(counts != {role: 10 for role in LEARNING_OPTION_ROLES} for counts in role_counts.values()):
        raise ValueError("learning v2 labels must be assigned each role exactly ten times")


@lru_cache(maxsize=1)
def load_learning_v2_content() -> dict[str, Any]:
    with LEARNING_V2_CONTENT_PATH.open("r", encoding="utf-8") as handle:
        content = yaml.safe_load(handle)
    if not isinstance(content, dict):
        raise ValueError("learning_questions_v2.yml must contain a mapping")
    _validate_v2_content(content, load_content())
    return content


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


def learning_question_spec(
    term_slug: str,
    learning_stage: str,
    variant_index: int = 1,
    content_version: int = LEGACY_LEARNING_CONTENT_VERSION,
) -> dict[str, Any]:
    term = content_term(term_slug)
    stage = learning_stage if learning_stage in LEARNING_STAGES else "conceptual_change"
    if content_version == LEGACY_LEARNING_CONTENT_VERSION:
        stage_data = term["learning"][stage]
        variants = stage_data["variants"]
        rotation = 0
    elif content_version == CURRENT_LEARNING_CONTENT_VERSION:
        stage_data = load_learning_v2_content()["terms"][term_slug][stage]
        variants = stage_data["variants"]
        term_index = ACTIVE_TERM_SLUGS.index(term_slug)
        stage_index = LEARNING_STAGES.index(stage)
        index = min(max(variant_index, 1), len(variants)) - 1
        ordinal = term_index * len(LEARNING_STAGES) * 5 + stage_index * 5 + index
        rotation = (ordinal * 3) % 9
    else:
        raise ValueError(f"unsupported learning content version: {content_version}")
    index = min(max(variant_index, 1), len(variants)) - 1
    variant = dict(variants[index])
    if content_version == CURRENT_LEARNING_CONTENT_VERSION:
        variant["body"] = f"{variant['scenario']}\n\n{variant['task']}"
        variant["options"] = _v2_options(variant, rotation)
        variant.pop("choices", None)
        variant.pop("scenario", None)
        variant.pop("task", None)
    variant["material"] = term["learning"][stage]["material"]
    variant["options"] = [
        {**option, "option_id": option["label"]} for option in variant.get("options") or []
    ]
    variant["question_type"] = "learning_multi_select"
    correct_labels = [option["label"] for option in variant["options"] if option.get("is_correct")]
    variant["expected_answer"] = f"{'、'.join(correct_labels)}をすべて選択し、それ以外を選ばない。"
    variant["selection_mode"] = "multiple"
    variant["min_selections"] = 3
    variant["max_selections"] = 3
    variant["_content_version"] = content_version
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
