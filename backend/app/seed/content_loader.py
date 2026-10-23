from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


CONTENT_PATH = Path(__file__).with_name("content") / "learning_content.yml"
UNUSED_CONTENT_PATH = Path(__file__).with_name("content") / "learning_questions_v2_unused.yml"
LEARNING_V3_CONTENT_PATH = Path(__file__).with_name("content") / "learning_questions_v3.yml"
ACTIVE_TERM_SLUGS = ("llm_knowledge", "multi_agent", "memory_process")
QUESTION_PHASES = ("pretest", "retest")
LEARNING_STAGES = ("enrichment", "conceptual_change")
LEARNING_SESSION_VARIANT_COUNT = 3
CURRENT_LEARNING_CONTENT_VERSION = 3
LEARNING_OPTION_ROLES = ("correct", "M1", "M3")
LEARNING_SCENARIO_TYPES = ("application", "prediction", "comparison", "boundary", "diagnosis")
ASSESSMENT_OPTION_ROLES = ("correct", "M1", "M3")
ASSESSMENT_VARIANT_COUNTS = {"pretest": 1, "retest": 3}
ASSESSMENT_ROLE_SLOTS = ("correct", "correct", "correct", "M1", "M1", "M1", "M3", "M3", "M3")
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


def _assessment_options(variant: dict[str, Any]) -> list[dict[str, Any]]:
    choices = variant["choices"]
    options = []
    for label_index, label in enumerate("ABCDEFGHI"):
        # Temporary issue-124 debug mapping; restore balanced positions before data collection.
        slot = label_index
        role = ASSESSMENT_ROLE_SLOTS[slot]
        body = choices[role][slot % 3]
        options.append(
            {
                "label": label,
                "body": body,
                "is_correct": role == "correct",
                "misconception_type": None if role == "correct" else role,
            }
        )
    options.append(dict(UNKNOWN_OPTION))
    return options


def _validate_option_set(name: str, options: Any) -> None:
    if not isinstance(options, list) or len(options) != 10:
        raise ValueError(f"{name} must contain exactly 10 options")
    labels = [option.get("label") for option in options]
    if labels != list("ABCDEFGHIJ"):
        raise ValueError(f"{name} labels must be A-J")
    correct = [option for option in options if option.get("is_correct")]
    if [option["label"] for option in correct] != ["A", "B", "C"]:
        raise ValueError(f"{name} must mark A-C as the only correct options")
    expected_types = {
        **{label: None for label in "ABC"},
        **{label: "M1" for label in "DEF"},
        **{label: "M3" for label in "GHI"},
        "J": "unknown",
    }
    for option in options:
        label = option["label"]
        expected_correct = label in "ABC"
        if bool(option.get("is_correct")) is not expected_correct:
            raise ValueError(f"{name} has an incorrect role for option {label}")
        if option.get("misconception_type") != expected_types[label]:
            raise ValueError(f"{name} has an incorrect role for option {label}")
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
        options = (
            _assessment_options(first_pretest)
            if first_pretest.get("choices")
            else first_pretest.get("options") or []
        )
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


def _validate_content(content: dict[str, Any]) -> None:
    if tuple(term.get("slug") for term in content.get("terms", [])) != ACTIVE_TERM_SLUGS:
        raise ValueError(f"active terms must be exactly {ACTIVE_TERM_SLUGS}")
    policy = content.get("selection_policy") or {}
    if (
        policy.get("scored_labels") != list("ABCDEFGHI")
        or policy.get("correct_count") != 3
        or policy.get("misconception_counts") != {"M1": 3, "M3": 3}
        or policy.get("unknown_label") != "J"
        or policy.get("classification_priority") != ["M3", "M1", "unknown"]
    ):
        raise ValueError("assessment selection policy is invalid")

    all_bodies: set[str] = set()
    all_choice_bodies: set[str] = set()

    for term in content["terms"]:
        slug = term["slug"]
        if not term.get("description") or not term.get("keywords") or not term.get("rag_sections"):
            raise ValueError(f"{slug} is missing metadata")
        questions = term.get("questions") or {}
        for phase in QUESTION_PHASES:
            variants = questions.get(phase) or []
            expected_count = ASSESSMENT_VARIANT_COUNTS[phase]
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
                _validate_assessment_variant(slug, phase, variant)
                body = f"{variant['scenario']}\n\n{variant['task']}"
                if body in all_bodies:
                    raise ValueError("assessment question bodies must be unique")
                all_bodies.add(body)
                options = _assessment_options(variant)
                _validate_option_set(f"{slug}.{phase}.{variant['variant_key']}", options)
                visible_bodies = [option["body"] for option in options[:9]]
                if len(set(visible_bodies)) != 9:
                    raise ValueError(f"{slug}.{phase}.{variant['variant_key']} has duplicate choices")
                if any(option_body in all_choice_bodies for option_body in visible_bodies):
                    raise ValueError("assessment choices must not be reused across variants")
                all_choice_bodies.update(visible_bodies)
        if _contains_langgraph(term) or _contains_langgraph(term.get("rag_sections")):
            raise ValueError(f"{slug} must not mention LangGraph")

    if sum(ASSESSMENT_VARIANT_COUNTS.values()) * len(ACTIVE_TERM_SLUGS) != 12:
        raise ValueError("assessment bank must contain exactly 21 variants")
    _validate_teaching_targets(content)


def _validate_assessment_variant(term_slug: str, phase: str, variant: Any) -> None:
    name = f"{term_slug}.{phase}.{variant.get('variant_key') if isinstance(variant, dict) else 'unknown'}"
    if not isinstance(variant, dict) or not variant.get("variant_key"):
        raise ValueError(f"{name} is invalid")
    if not str(variant.get("scenario") or "").strip() or not str(variant.get("task") or "").strip():
        raise ValueError(f"{name} needs a scenario and task")
    choices = variant.get("choices")
    if not isinstance(choices, dict) or tuple(choices) != ASSESSMENT_OPTION_ROLES:
        raise ValueError(f"{name} must define correct, M1, and M3 choices")
    texts: list[str] = []
    for role in ASSESSMENT_OPTION_ROLES:
        items = choices.get(role)
        if not isinstance(items, list) or len(items) != 3 or any(not str(item).strip() for item in items):
            raise ValueError(f"{name} needs three nonempty {role} choices")
        texts.extend(str(item).strip() for item in items)
    lengths = [len(text) for text in texts]
    if min(lengths) < 20 or max(lengths) > min(lengths) * 1.8 or max(lengths) - min(lengths) > 32:
        raise ValueError(f"{name} has a conspicuous option-length spread")
    if len(set(texts)) != len(texts):
        raise ValueError(f"{name} has duplicate choice text")
    if _contains_langgraph(variant):
        raise ValueError(f"{name} must not mention LangGraph")


def _learning_options(variant: dict[str, Any]) -> list[dict[str, Any]]:
    choices = variant["choices"]
    options = []
    role_slots = ("correct", "correct", "correct", "M1", "M1", "M1", "M3", "M3", "M3")
    for label_index, label in enumerate("ABCDEFGHI"):
        role = role_slots[label_index]
        role_index = label_index % 3
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


def assessment_question_spec(term_slug: str, phase: str, variant_index: int = 1) -> dict[str, Any]:
    if phase == "final_test":
        # The route remains for compatibility, but it uses the first post-pretest
        # question rather than maintaining a separate final_test variant.
        source_phase = "retest"
        variant_index = 1
    elif phase in QUESTION_PHASES:
        source_phase = phase
    else:
        raise ValueError(f"unsupported assessment phase: {phase}")
    variants = content_term(term_slug)["questions"][source_phase]
    index = min(max(variant_index, 1), len(variants)) - 1
    variant = dict(variants[index])
    variant["body"] = f"{variant['scenario']}\n\n{variant['task']}"
    variant["options"] = _assessment_options(variant)
    correct_labels = [option["label"] for option in variant["options"] if option["is_correct"]]
    variant["expected"] = f"{'、'.join(correct_labels)}をすべて選択し、それ以外を選ばない。"
    return variant


def _validate_v3_content(content: dict[str, Any], assessment_content: dict[str, Any]) -> None:
    if content.get("version") != CURRENT_LEARNING_CONTENT_VERSION:
        raise ValueError("learning_questions_v3.yml must have version 3")
    terms = content.get("terms") or {}
    if tuple(terms) != ACTIVE_TERM_SLUGS:
        raise ValueError(f"learning v3 terms must be exactly {ACTIVE_TERM_SLUGS}")

    assessment_bodies = {
        f"{variant['scenario']}\n\n{variant['task']}"
        for term in assessment_content["terms"]
        for phase in QUESTION_PHASES
        for variant in (term.get("questions") or {}).get(phase, [])
    }
    assessment_options = {
        option["body"]
        for term in assessment_content["terms"]
        for phase in QUESTION_PHASES
        for variant in (term.get("questions") or {}).get(phase, [])
        for option in _assessment_options(variant)[:9]
    }
    variant_count = 0
    learning_bodies: set[str] = set()
    learning_option_bodies: set[str] = set()

    for term_slug in ACTIVE_TERM_SLUGS:
        term_data = terms.get(term_slug) or {}
        if tuple(term_data) != ("variants",):
            raise ValueError(f"learning v3 term {term_slug} must contain only variants")
        variants = term_data.get("variants") or []
        if len(variants) != LEARNING_SESSION_VARIANT_COUNT:
            raise ValueError(
                f"{term_slug} must contain {LEARNING_SESSION_VARIANT_COUNT} learning-round variants"
            )
        expected_keys = [
            f"learning_round_v{index}"
            for index in range(1, LEARNING_SESSION_VARIANT_COUNT + 1)
        ]
        if [variant.get("variant_key") for variant in variants] != expected_keys:
            raise ValueError(f"{term_slug} must use variant keys {expected_keys}")
        if [variant.get("scenario_type") for variant in variants] != list(
            LEARNING_SCENARIO_TYPES[:LEARNING_SESSION_VARIANT_COUNT]
        ):
            raise ValueError(
                f"{term_slug} must cover the first three learning scenario types once in order"
            )

        for variant in variants:
            name = f"{term_slug}.{variant.get('variant_key')}"
            if not str(variant.get("scenario") or "").strip() or not str(variant.get("task") or "").strip():
                raise ValueError(f"{name} needs scenario and task")
            choices = variant.get("choices") or {}
            if tuple(choices) != LEARNING_OPTION_ROLES:
                raise ValueError(f"{name} must define correct, M1, and M3 choices")
            all_choice_bodies = []
            for role in LEARNING_OPTION_ROLES:
                texts = choices.get(role)
                if (
                    not isinstance(texts, list)
                    or len(texts) != 3
                    or any(not str(text).strip() for text in texts)
                ):
                    raise ValueError(f"{name} needs three nonempty {role} choices")
                all_choice_bodies.extend(str(text).strip() for text in texts)
            lengths = [len(text) for text in all_choice_bodies]
            if (
                min(lengths) < 20
                or max(lengths) > min(lengths) * 1.8
                or max(lengths) - min(lengths) > 32
            ):
                raise ValueError(f"{name} has a conspicuous option-length spread")
            body = f"{variant['scenario']}\n\n{variant['task']}"
            if body in learning_bodies:
                raise ValueError("learning v3 question bodies must be unique")
            learning_bodies.add(body)
            if any(body in learning_option_bodies for body in all_choice_bodies):
                raise ValueError("learning v3 choices must be unique across variants")
            learning_option_bodies.update(all_choice_bodies)
            if len(set(all_choice_bodies)) != 9:
                raise ValueError(f"{name} has duplicate choices")
            if any(body in assessment_bodies or body in assessment_options for body in all_choice_bodies):
                raise ValueError(f"{name} copies fixed test wording")
            if _contains_langgraph(variant):
                raise ValueError(f"{name} must not mention LangGraph")
            _validate_option_set(name, _learning_options(variant))
            variant_count += 1

    expected_variant_count = len(ACTIVE_TERM_SLUGS) * LEARNING_SESSION_VARIANT_COUNT
    if variant_count != expected_variant_count:
        raise ValueError(
            f"learning v3 bank must contain exactly {expected_variant_count} variants"
        )


@lru_cache(maxsize=1)
def load_learning_v3_content() -> dict[str, Any]:
    with LEARNING_V3_CONTENT_PATH.open("r", encoding="utf-8") as handle:
        content = yaml.safe_load(handle)
    if not isinstance(content, dict):
        raise ValueError("learning_questions_v3.yml must contain a mapping")
    _validate_v3_content(content, load_content())
    return content


def _archived_assessment_variants() -> dict[str, dict[str, list[dict[str, Any]]]]:
    with UNUSED_CONTENT_PATH.open("r", encoding="utf-8") as handle:
        archive = yaml.safe_load(handle)
    section = archive.get("unused_assessment_questions") if isinstance(archive, dict) else None
    terms = section.get("terms") if isinstance(section, dict) else None
    if not isinstance(terms, dict) or tuple(terms) != ACTIVE_TERM_SLUGS:
        raise ValueError("unused assessment archive must contain all active terms")
    expected_keys = ("retest_v4", "retest_v5")
    for term_slug in ACTIVE_TERM_SLUGS:
        term_data = terms.get(term_slug) or {}
        variants = term_data.get("retest") or []
        if [variant.get("variant_key") for variant in variants] != list(expected_keys):
            raise ValueError(f"unused assessment archive for {term_slug} must contain retest_v4 and retest_v5")
        final_variants = term_data.get("final_test") or []
        if [variant.get("variant_key") for variant in final_variants] != ["final_test_v1"]:
            raise ValueError(f"unused assessment archive for {term_slug} must contain final_test_v1")
    return terms


@lru_cache(maxsize=1)
def load_content() -> dict[str, Any]:
    with CONTENT_PATH.open("r", encoding="utf-8") as handle:
        content = yaml.safe_load(handle)
    if not isinstance(content, dict):
        raise ValueError("learning_content.yml must contain a mapping")

    # Validate retired questions separately, but keep them out of the active
    # content object so normal seed/debug inspection sees only active questions.
    _archived_assessment_variants()
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
) -> dict[str, Any]:
    content_term(term_slug)
    # The semantic learning stage controls the tutoring prompt only. The
    # question is selected by the learning-session round and is shared by
    # enrichment and conceptual_change.
    variants = load_learning_v3_content()["terms"][term_slug]["variants"]
    index = min(max(variant_index, 1), len(variants)) - 1
    variant = dict(variants[index])
    variant["body"] = f"{variant['scenario']}\n\n{variant['task']}"
    variant["options"] = _learning_options(variant)
    variant.pop("choices", None)
    variant.pop("scenario", None)
    variant.pop("task", None)
    variant["options"] = [
        {**option, "option_id": option["label"]} for option in variant.get("options") or []
    ]
    variant["question_type"] = "learning_multi_select"
    correct_labels = [option["label"] for option in variant["options"] if option.get("is_correct")]
    variant["expected_answer"] = f"{'、'.join(correct_labels)}をすべて選択し、それ以外を選ばない。"
    variant["selection_mode"] = "multiple"
    variant["min_selections"] = 3
    variant["max_selections"] = 3
    variant["_content_version"] = CURRENT_LEARNING_CONTENT_VERSION
    return variant


def seed_terms() -> list[dict[str, Any]]:
    terms: list[dict[str, Any]] = []
    for term in load_content()["terms"]:
        normalized_questions: dict[str, Any] = {
            "pretest": {
                **assessment_question_spec(term["slug"], "pretest"),
                "options": _option_tuples(assessment_question_spec(term["slug"], "pretest")["options"]),
            },
            "retest": [
                {
                    **assessment_question_spec(term["slug"], "retest", index),
                    "options": _option_tuples(assessment_question_spec(term["slug"], "retest", index)["options"]),
                }
                for index in range(1, ASSESSMENT_VARIANT_COUNTS["retest"] + 1)
            ],
            "final_test": {
                **assessment_question_spec(term["slug"], "final_test"),
                "options": _option_tuples(assessment_question_spec(term["slug"], "final_test")["options"]),
            },
        }
        terms.append({**term, "questions": normalized_questions})
    return terms
