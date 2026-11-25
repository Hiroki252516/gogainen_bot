from __future__ import annotations

from app.core.config import get_settings


ALLOWED_REASONING_EFFORTS = ("low", "medium", "high", "xhigh", "max")
ALLOWED_MODELS = ("gpt-6.1-sol", "gpt-6-luna", "gpt-6-astra")
STUDY_MODEL = "gpt-6-luna"
STUDY_REASONING_EFFORT = "low"

def normalize_reasoning_effort(value: str) -> str:
    if value not in ALLOWED_REASONING_EFFORTS:
        allowed = ", ".join(ALLOWED_REASONING_EFFORTS)
        raise ValueError(f"reasoning effort must be one of: {allowed}")
    return value


def normalize_model(value: str) -> str:
    if value not in ALLOWED_MODELS:
        allowed = ", ".join(ALLOWED_MODELS)
        raise ValueError(f"model must be one of: {allowed}")
    return value


def current_ai_runtime_settings() -> tuple[str, str, bool]:
    settings = get_settings()
    return settings.codex_model, normalize_reasoning_effort(settings.codex_reasoning_effort), True


def current_model() -> str:
    return current_ai_runtime_settings()[0]


def current_reasoning_effort() -> str:
    return current_ai_runtime_settings()[1]


def current_fast_mode() -> bool:
    return current_ai_runtime_settings()[2]


def set_reasoning_effort(value: str) -> str:
    raise ValueError("reasoning effort is fixed by CODEX_REASONING_EFFORT")


def set_model(value: str) -> str:
    raise ValueError("model is fixed by CODEX_MODEL")


def set_fast_mode(enabled: bool) -> bool:
    if type(enabled) is not bool:
        raise ValueError("fast mode must be a boolean")
    if not enabled:
        raise ValueError("fast mode is fixed on")
    return True


def reset_reasoning_effort_override() -> None:
    """Compatibility no-op: reasoning effort comes from the environment."""


def reset_model_override() -> None:
    """Compatibility no-op: the model comes from the environment."""


def reset_fast_mode_override() -> None:
    """Compatibility no-op: Fast mode is fixed on."""
