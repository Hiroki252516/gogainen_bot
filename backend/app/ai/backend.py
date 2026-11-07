from __future__ import annotations

from typing import Any, Protocol

from app.ai.prompt_config import PROMPT_TEXT


_TEACHING_STRATEGIES = PROMPT_TEXT["research_config"]["teaching_strategies"]


class AIBackend(Protocol):
    provider: str

    async def generate_tutoring_turn(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def generate_correct_answer_summary(self, payload: dict[str, Any]) -> dict[str, Any]: ...

    async def explain_selected_distractor(self, payload: dict[str, Any]) -> dict[str, Any]: ...


def strategy_for(misconception_type: str | None, status: str | None, group_condition: str) -> str:
    if group_condition == "control":
        return _TEACHING_STRATEGIES["control"]
    proposed = _TEACHING_STRATEGIES["proposed"]
    by_type = proposed["by_type"]
    if misconception_type == "M1":
        return by_type["M1"]
    if misconception_type == "M3":
        return by_type["M3"]
    if misconception_type == "unknown":
        return by_type["unknown"]
    if status == "unknown":
        return proposed["by_status"]["unknown"]
    raise ValueError(f"unsupported teaching type: {misconception_type!r}")
