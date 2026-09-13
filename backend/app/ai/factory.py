from app.ai.codex_app_server_backend import CodexAppServerBackend
from app.ai.mock_backend import MockAIBackend
from app.core.config import get_settings


def get_ai_backend(reasoning_effort: str | None = None):
    settings = get_settings()
    if settings.ai_backend == "codex_app_server":
        return CodexAppServerBackend(reasoning_effort=reasoning_effort)
    return MockAIBackend()
