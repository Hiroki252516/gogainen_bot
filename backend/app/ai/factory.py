from app.ai.codex_app_server_backend import CodexAppServerBackend
from app.ai.mock_backend import MockAIBackend
from app.core.config import get_settings
from app.core.runtime_config import current_ai_runtime_settings


def get_ai_backend(reasoning_effort: str | None = None, model: str | None = None):
    settings = get_settings()
    if settings.ai_backend == "codex_app_server":
        current_model, current_effort = (None, None)
        if model is None or reasoning_effort is None:
            current_model, current_effort = current_ai_runtime_settings()
        return CodexAppServerBackend(
            model=model if model is not None else current_model,
            reasoning_effort=reasoning_effort if reasoning_effort is not None else current_effort,
        )
    return MockAIBackend()
