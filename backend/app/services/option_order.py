from __future__ import annotations

import hashlib
import uuid
from typing import Any

from app.seed.content_loader import ACTIVE_TERM_SLUGS, LEARNING_STAGES
from app.models import RuntimeSetting


DEBUG_FIXED = "debug_fixed"
RANDOMIZED = "randomized"
OPTION_ORDER_MODES = (DEBUG_FIXED, RANDOMIZED)
OPTION_LABELS = tuple("ABCDEFGHIJ")
SHUFFLED_OPTION_LABELS = OPTION_LABELS[:-1]
UNKNOWN_DISPLAY_LABEL = OPTION_LABELS[-1]
OPTION_ORDER_VERSION = "option-order-v2-unknown-last"
ASSESSMENT_VARIANTS_PER_TERM = 7
LEARNING_VARIANTS_PER_STAGE = 5


def effective_option_order_mode(value: str | None) -> str:
    return value if value in OPTION_ORDER_MODES else DEBUG_FIXED


def current_option_order_mode(db: Any) -> str:
    setting = db.get(RuntimeSetting, 1)
    return effective_option_order_mode(setting.option_order_mode if setting else None)


def save_option_order_mode(db: Any, mode: str) -> str:
    if mode not in OPTION_ORDER_MODES:
        raise ValueError("unsupported option order mode")
    setting = db.get(RuntimeSetting, 1)
    if setting is None:
        setting = RuntimeSetting(id=1, option_order_mode=mode)
        db.add(setting)
    else:
        setting.option_order_mode = mode
    db.commit()
    return mode


def assessment_bank_index(term_slug: str, phase: str, variant_key: str) -> int:
    if not isinstance(variant_key, str) or not variant_key:
        raise ValueError(f"invalid assessment variant key: {variant_key}")
    term_index = ACTIVE_TERM_SLUGS.index(term_slug)
    phase_offsets = {"pretest": 0, "retest": 1, "final_test": 6}
    if phase not in phase_offsets:
        raise ValueError(f"unsupported assessment phase: {phase}")
    try:
        variant_index = int(variant_key.rsplit("_v", 1)[1])
    except (IndexError, ValueError) as exc:
        raise ValueError(f"invalid assessment variant key: {variant_key}") from exc
    if phase == "retest" and not 1 <= variant_index <= 5:
        raise ValueError(f"invalid retest variant: {variant_key}")
    if phase != "retest" and variant_index != 1:
        raise ValueError(f"invalid {phase} variant: {variant_key}")
    offset = phase_offsets[phase] + (variant_index - 1 if phase == "retest" else 0)
    return term_index * ASSESSMENT_VARIANTS_PER_TERM + offset


def learning_bank_index(term_slug: str, learning_stage: str, variant_index: int) -> int:
    term_index = ACTIVE_TERM_SLUGS.index(term_slug)
    stage_index = LEARNING_STAGES.index(learning_stage)
    if not 1 <= variant_index <= LEARNING_VARIANTS_PER_STAGE:
        raise ValueError(f"invalid learning variant index: {variant_index}")
    return (
        term_index * len(LEARNING_STAGES) * LEARNING_VARIANTS_PER_STAGE
        + stage_index * LEARNING_VARIANTS_PER_STAGE
        + variant_index
        - 1
    )


def option_role(option: Any) -> str:
    is_correct = option.is_correct if hasattr(option, "is_correct") else option.get("is_correct")
    misconception_type = (
        option.misconception_type
        if hasattr(option, "misconception_type")
        else option.get("misconception_type")
    )
    if is_correct:
        return "correct"
    if misconception_type in {"M1", "M3", "unknown"}:
        return misconception_type
    raise ValueError("option has no supported scoring role")


def _source_label(option: Any) -> str:
    label = option.option_label if hasattr(option, "option_label") else option.get("label")
    if label not in OPTION_LABELS:
        raise ValueError("option has no stable source label")
    return str(label)


def _option_id(option: Any) -> str:
    value = option.id if hasattr(option, "id") else option.get("option_id")
    if value is None:
        value = _source_label(option)
    return str(value)


def _option_body(option: Any) -> str:
    value = option.body if hasattr(option, "body") else option.get("body")
    return str(value)


def _participant_option_id(option: Any, *, bank: str, mode: str) -> str:
    if bank == "learning" and mode == RANDOMIZED:
        # The ID is persisted with the displayed turn; it must not encode the source label.
        return f"lo_{uuid.uuid4().hex}"
    return _option_id(option)


def _label_permutation(bank: str, block_index: int) -> list[str]:
    return sorted(
        SHUFFLED_OPTION_LABELS,
        key=lambda label: hashlib.sha256(
            f"{OPTION_ORDER_VERSION}:{bank}:{block_index}:label:{label}".encode()
        ).digest(),
    )


def _display_label_by_source(options: list[Any], bank: str, item_index: int) -> dict[str, str]:
    if len(options) != 10:
        raise ValueError("randomized option order requires exactly ten options")

    by_role: dict[str, list[Any]] = {"correct": [], "M1": [], "M3": [], "unknown": []}
    for option in options:
        by_role[option_role(option)].append(option)
    if tuple(len(by_role[role]) for role in ("correct", "M1", "M3", "unknown")) != (3, 3, 3, 1):
        raise ValueError("randomized option order requires role counts 3/3/3/1")

    # Rotate roles over each block of three questions so every A-I label is
    # used once per role. Re-shuffle between blocks to vary the correct slots.
    labels = _label_permutation(bank, item_index // 3)
    label_count = len(labels)
    start = (item_index % 3) * 3
    slots = {
        "correct": [labels[(start + offset) % label_count] for offset in range(0, 3)],
        "M1": [labels[(start + offset) % label_count] for offset in range(3, 6)],
        "M3": [labels[(start + offset) % label_count] for offset in range(6, 9)],
        "unknown": [UNKNOWN_DISPLAY_LABEL],
    }
    result: dict[str, str] = {}
    for role, role_options in by_role.items():
        role_options = sorted(
            role_options,
            key=lambda option: hashlib.sha256(
                f"{OPTION_ORDER_VERSION}:{bank}:{item_index}:{role}:{_source_label(option)}".encode()
            ).digest(),
        )
        result.update(
            {_source_label(option): label for option, label in zip(role_options, slots[role], strict=True)}
        )
    return result


def present_options(
    options: list[Any],
    *,
    mode: str | None,
    bank: str,
    item_index: int,
) -> list[dict[str, Any]]:
    """Return a visible layout with IDs that do not encode learning-option roles."""
    selected_mode = effective_option_order_mode(mode)
    display_labels = (
        _display_label_by_source(options, bank, item_index)
        if selected_mode == RANDOMIZED
        else {_source_label(option): _source_label(option) for option in options}
    )
    displayed = [
        {
            "option_id": _participant_option_id(option, bank=bank, mode=selected_mode),
            "label": display_labels[_source_label(option)],
            "body": _option_body(option),
            "exclusive": option_role(option) == "unknown",
        }
        for option in options
    ]
    if selected_mode == RANDOMIZED:
        displayed.sort(key=lambda option: option["label"])
    return displayed
