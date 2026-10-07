from __future__ import annotations

from typing import Any, Protocol


class AIBackend(Protocol):
    provider: str

    async def generate_tutoring_turn(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def generate_correct_answer_summary(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def explain_selected_distractor(self, payload: dict[str, Any]) -> dict[str, Any]: ...


def strategy_for(misconception_type: str | None, status: str | None, group_condition: str) -> str:
    if group_condition == "control":
        return "general_explanation"
    if misconception_type == "M1":
        return "belief_revision"
    if misconception_type == "M3":
        return "category_reorientation"
    if status == "unknown" or misconception_type == "unknown":
        return "foundational_explanation"
    raise ValueError(f"unsupported teaching type: {misconception_type!r}")
