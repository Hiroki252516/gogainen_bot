import asyncio

import pytest

from admin_client import AuthenticatedTestClient
from app.ai.codex_app_server_backend import CodexAppServerBackend
from app.core.config import get_settings
from app.core.runtime_config import (
    ALLOWED_MODELS,
    ALLOWED_REASONING_EFFORTS,
    current_ai_runtime_settings,
    reset_fast_mode_override,
    reset_model_override,
    reset_reasoning_effort_override,
    set_fast_mode,
)
from app.main import app


@pytest.fixture(autouse=True)
def reset_runtime_overrides():
    reset_model_override()
    reset_reasoning_effort_override()
    reset_fast_mode_override()
    yield
    reset_model_override()
    reset_reasoning_effort_override()
    reset_fast_mode_override()


def test_admin_ai_api_exposes_and_accepts_all_model_and_effort_options(monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_backend", "codex_app_server")

    async def fake_status(self):
        return {"app_server_reachable": True, "logged_in": True}

    monkeypatch.setattr(CodexAppServerBackend, "status", fake_status)
    client = AuthenticatedTestClient(app)

    status = client.get("/api/admin/ai/status")
    assert status.status_code == 200
    assert status.json()["allowed_models"] == list(ALLOWED_MODELS)
    assert status.json()["allowed_reasoning_efforts"] == list(ALLOWED_REASONING_EFFORTS)
    assert status.json()["fast_mode"] is False
    assert status.json()["can_change_fast_mode"] is True
    assert status.json()["fast_mode_applies"] is True

    for model in ALLOWED_MODELS:
        response = client.post("/api/admin/ai/model", json={"model": model})
        assert response.status_code == 200
        assert response.json()["model"] == model

    for effort in ALLOWED_REASONING_EFFORTS:
        response = client.post("/api/admin/ai/reasoning-effort", json={"reasoning_effort": effort})
        assert response.status_code == 200
        assert response.json()["reasoning_effort"] == effort

    assert client.post("/api/admin/ai/model", json={"model": "unknown-model"}).status_code == 422
    assert client.post("/api/admin/ai/reasoning-effort", json={"reasoning_effort": "ultra"}).status_code == 422

    enabled = client.post("/api/admin/ai/fast-mode", json={"enabled": True})
    assert enabled.status_code == 200
    assert enabled.json()["fast_mode"] is True
    disabled = client.post("/api/admin/ai/fast-mode", json={"enabled": False})
    assert disabled.status_code == 200
    assert disabled.json()["fast_mode"] is False
    for value in ("true", 1, None):
        assert client.post("/api/admin/ai/fast-mode", json={"enabled": value}).status_code == 422


def test_fast_mode_is_process_local_and_defaults_off():
    assert current_ai_runtime_settings()[2] is False
    assert set_fast_mode(True) is True
    assert current_ai_runtime_settings()[2] is True
    reset_fast_mode_override()
    assert current_ai_runtime_settings()[2] is False


def test_fast_mode_api_is_disabled_for_mock_backend(monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_backend", "mock")
    client = AuthenticatedTestClient(app)

    status = client.get("/api/admin/ai/status")
    assert status.json()["fast_mode"] is False
    assert status.json()["can_change_fast_mode"] is False
    assert status.json()["fast_mode_applies"] is False
    assert client.post("/api/admin/ai/fast-mode", json={"enabled": True}).status_code == 409


@pytest.mark.parametrize("model", ALLOWED_MODELS)
@pytest.mark.parametrize("effort", ["xhigh", "max"])
@pytest.mark.parametrize("fast_mode", [False, True])
def test_app_server_receives_selected_settings_in_payload_and_audit(monkeypatch, model, effort, fast_mode):
    calls = []

    class FakeRpc:
        async def call(self, method, params=None, **kwargs):
            calls.append((method, params))
            on_sent = kwargs.get("on_sent")
            if on_sent:
                on_sent()
            if method == "account/read":
                return {"account": {"id": "test-account"}}
            if method == "thread/start":
                return {"thread": {"id": "thread-1"}}
            if method == "turn/start":
                return {"turn": {"id": "turn-1"}}
            return {}

        async def notify(self, method, params):
            return None

        async def recv(self, notification_handler):
            notification_handler({
                "method": "item/completed",
                "params": {
                    "turnId": "turn-1",
                    "item": {"type": "agentMessage", "text": '{"ok":true}'},
                },
            })
            return {
                "method": "turn/completed",
                "params": {"turn": {"id": "turn-1", "status": "completed"}},
            }

    class FakeClientContext:
        async def __aenter__(self):
            return FakeRpc()

        async def __aexit__(self, *_args):
            return False

    backend = CodexAppServerBackend(model=model, reasoning_effort=effort, fast_mode=fast_mode)
    monkeypatch.setattr(backend, "_client", lambda: FakeClientContext())
    result = asyncio.run(backend._run_structured_turn(
        "runtime-settings-test",
        "Return a JSON object with ok=true.",
        {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
    ))

    thread_payload = next(params for method, params in calls if method == "thread/start")
    turn_payload = next(params for method, params in calls if method == "turn/start")
    assert thread_payload["model"] == model
    assert turn_payload["model"] == model
    assert turn_payload["effort"] == effort
    assert turn_payload["serviceTierForTurn"] == ("fast" if fast_mode else "default")
    assert result.request_audit["model"] == model
    assert result.request_audit["reasoning_effort"] == effort
    assert result.request_audit["fast_mode"] is fast_mode
    assert result.request_audit["turn_start_params"]["effort"] == effort
    assert result.request_audit["turn_start_params"]["serviceTierForTurn"] == ("fast" if fast_mode else "default")
