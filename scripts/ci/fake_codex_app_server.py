#!/usr/bin/env python3
"""Unauthenticated Codex app-server protocol stub for Compose socket tests."""

import asyncio
import json
import os
import sys
from pathlib import Path

import websockets


async def handle(connection):
    async for raw_message in connection:
        message = json.loads(raw_message)
        method = message.get("method")
        request_id = message.get("id")
        if request_id is None:
            continue

        if method == "initialize":
            result = {}
        elif method == "account/read":
            result = {"account": None}
        else:
            await connection.send(json.dumps({
                "id": request_id,
                "error": {"code": -32601, "message": f"Unsupported method: {method}"},
            }))
            continue

        await connection.send(json.dumps({"id": request_id, "result": result}))


async def serve_unix(socket_path: Path):
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    async with websockets.unix_serve(handle, path=str(socket_path)) as server:
        os.chmod(socket_path, 0o666)
        print(f"READY {socket_path}", flush=True)
        await server.serve_forever()


async def serve_tcp(host: str, port: int, port_file: Path):
    async with websockets.serve(handle, host=host, port=port) as server:
        actual_port = server.sockets[0].getsockname()[1]
        port_file.write_text(str(actual_port), encoding="ascii")
        print(f"READY {host}:{actual_port}", flush=True)
        await server.serve_forever()


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "unix" and len(sys.argv) == 3:
        asyncio.run(serve_unix(Path(sys.argv[2])))
    elif mode == "tcp" and len(sys.argv) == 5:
        asyncio.run(serve_tcp(sys.argv[2], int(sys.argv[3]), Path(sys.argv[4])))
    else:
        raise SystemExit("Usage: fake_codex_app_server.py unix SOCKET_PATH | tcp HOST PORT PORT_FILE")
