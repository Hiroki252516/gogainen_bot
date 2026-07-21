from __future__ import annotations

from typing import Any, Protocol


class AIBackend(Protocol):
    provider: str

    async def diagnose_answer(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def generate_tutoring_turn(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def grade_response(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def generate_feedback(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def summarize_learner_state(self, payload: dict[str, Any]) -> dict[str, Any]: ...


def strategy_for(misconception_type: str | None, status: str | None, group_condition: str) -> str:
    if group_condition == "control":
        return "general_explanation"
    if misconception_type == "M1":
        return "belief_revision"
    if misconception_type == "M3":
        return "category_reorientation"
    if status == "unknown" or misconception_type == "unknown":
        return "foundational_explanation"
    if status == "unstable_correct":
        return "self_explanation_check"
    return "self_explanation_check"


def initial_level(status: str, misconception_type: str | None, confidence: int | None) -> str:
    if status == "unknown":
        return "L3"
    if status == "misconception":
        return "L3"
    if status == "unstable_correct":
        return "L2"
    if status == "stable_correct":
        return "L2"
    if status == "transfer_ready":
        return "L2"
    return "L2"


def lower_level(level: str | None) -> str:
    order = ["L2", "L3"]
    if level not in order:
        return "L2"
    return order[max(0, order.index(level) - 1)]


def raise_level(level: str | None) -> str:
    order = ["L2", "L3"]
    if level not in order:
        return "L2"
    return order[min(len(order) - 1, order.index(level) + 1)]


def normalize_level(level: str | None) -> str:
    return level if level in {"L2", "L3"} else "L2"
