from __future__ import annotations

import json
from typing import Any

import websockets

from app.ai.mock_backend import MockAIBackend
from app.core.config import get_settings


class CodexAppServerBackend:
    provider = "codex_app_server"

    def __init__(self) -> None:
        self.settings = get_settings()
        self.mock = MockAIBackend()

    async def status(self) -> dict[str, Any]:
        try:
            async with websockets.connect(self.settings.codex_app_server_url, open_timeout=2) as ws:
                await ws.send(json.dumps({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "learning_log_ai_tutor", "version": "0.1.0"}, "capabilities": {}}}))
                await ws.recv()
            return {"app_server_reachable": True, "logged_in": None, "last_error": None}
        except Exception as exc:  # pragma: no cover - depends on local app-server
            return {"app_server_reachable": False, "logged_in": False, "last_error": str(exc)}

    async def _fallback(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = await getattr(self.mock, method)(payload)
        result["_fallback_provider"] = "mock"
        return result

    async def diagnose_answer(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._fallback("diagnose_answer", payload)

    async def generate_tutoring_turn(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._fallback("generate_tutoring_turn", payload)

    async def grade_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._fallback("grade_response", payload)

    async def generate_feedback(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._fallback("generate_feedback", payload)

    async def summarize_learner_state(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._fallback("summarize_learner_state", payload)
