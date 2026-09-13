from __future__ import annotations

from threading import Lock

from app.core.config import get_settings


ALLOWED_REASONING_EFFORTS = ("low", "medium", "high")

_lock = Lock()
_reasoning_effort_override: str | None = None


def normalize_reasoning_effort(value: str) -> str:
    if value not in ALLOWED_REASONING_EFFORTS:
        allowed = ", ".join(ALLOWED_REASONING_EFFORTS)
        raise ValueError(f"reasoning effort must be one of: {allowed}")
    return value


def current_reasoning_effort() -> str:
    with _lock:
        configured = _reasoning_effort_override or get_settings().codex_reasoning_effort
    return normalize_reasoning_effort(configured)


def set_reasoning_effort(value: str) -> str:
    normalized = normalize_reasoning_effort(value)
    global _reasoning_effort_override
    with _lock:
        _reasoning_effort_override = normalized
    return normalized


def reset_reasoning_effort_override() -> None:
    global _reasoning_effort_override
    with _lock:
        _reasoning_effort_override = None
