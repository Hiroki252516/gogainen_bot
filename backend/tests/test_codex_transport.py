import asyncio
import json
import socket

import pytest
import websockets

from app.ai.codex_app_server_backend import CodexAppServerBackend


@pytest.mark.parametrize("transport", ["websocket", "unix"])
def test_status_initializes_transport_before_reading_account(transport, tmp_path):
    if transport == "unix" and not hasattr(socket, "AF_UNIX"):
        pytest.skip("Unix sockets are unavailable")

    async def check():
        received = []

        async def serve(ws):
            request = json.loads(await ws.recv())
            received.append(request["method"])
            await ws.send(json.dumps({"id": request["id"], "result": {}}))
            ready = json.loads(await ws.recv())
            received.append(ready["method"])
            assert "id" not in ready
            request = json.loads(await ws.recv())
            received.append(request["method"])
            await ws.send(json.dumps({
                "id": request["id"],
                "result": {"account": {"type": "chatgpt", "planType": "test"}},
            }))

        if transport == "unix":
            path = str(tmp_path / "app.sock")
            listener = websockets.unix_serve(serve, path=path)
            url = f"unix://{path}"
        else:
            listener = websockets.serve(serve, "127.0.0.1", 0)
        async with listener as server:
            if transport == "websocket":
                url = f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"
            backend = CodexAppServerBackend()
            backend.settings = backend.settings.model_copy(update={
                "codex_app_server_url": url,
                "codex_ws_token_file": None,
                "codex_turn_timeout_sec": 2,
            })
            status = await backend.status()
        assert status["app_server_reachable"] is True, status
        assert status["logged_in"] is True
        assert received == ["initialize", "initialized", "account/read"]

    asyncio.run(check())


def test_unix_connection_failure_is_reported_without_mock(tmp_path):
    backend = CodexAppServerBackend()
    backend.settings = backend.settings.model_copy(update={
        "codex_app_server_url": f"unix://{tmp_path / 'absent.sock'}",
        "codex_ws_token_file": None,
    })
    status = asyncio.run(backend.status())
    assert status["app_server_reachable"] is False
    assert status["logged_in"] is False
    assert status["last_error"]
