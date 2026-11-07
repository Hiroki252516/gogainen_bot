from __future__ import annotations

from threading import Lock

from app.core.config import get_settings


ALLOWED_REASONING_EFFORTS = ("low", "medium", "high", "xhigh", "max")
ALLOWED_MODELS = ("gpt-6.1-sol", "gpt-6-luna", "gpt-6-astra")
STUDY_MODEL = "gpt-6-luna"
STUDY_REASONING_EFFORT = "low"

_lock = Lock()
_reasoning_effort_override: str | None = None
_model_override: str | None = None
_fast_mode_override: bool | None = None


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
    with _lock:
        settings = get_settings()
        model = _model_override or settings.codex_model
        effort = _reasoning_effort_override or settings.codex_reasoning_effort
        fast_mode = _fast_mode_override if _fast_mode_override is not None else False
    return model, normalize_reasoning_effort(effort), fast_mode


def current_model() -> str:
    return current_ai_runtime_settings()[0]


def current_reasoning_effort() -> str:
    return current_ai_runtime_settings()[1]


def current_fast_mode() -> bool:
    return current_ai_runtime_settings()[2]


def set_reasoning_effort(value: str) -> str:
    normalized = normalize_reasoning_effort(value)
    global _reasoning_effort_override
    with _lock:
        _reasoning_effort_override = normalized
    return normalized


def set_model(value: str) -> str:
    normalized = normalize_model(value)
    global _model_override
    with _lock:
        _model_override = normalized
    return normalized


def set_fast_mode(enabled: bool) -> bool:
    if type(enabled) is not bool:
        raise ValueError("fast mode must be a boolean")
    global _fast_mode_override
    with _lock:
        _fast_mode_override = enabled
    return enabled


def reset_reasoning_effort_override() -> None:
    global _reasoning_effort_override
    with _lock:
        _reasoning_effort_override = None


def reset_model_override() -> None:
    global _model_override
    with _lock:
        _model_override = None


def reset_fast_mode_override() -> None:
    global _fast_mode_override
    with _lock:
        _fast_mode_override = None
