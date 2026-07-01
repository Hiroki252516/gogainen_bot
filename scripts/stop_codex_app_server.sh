#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PID_FILE="$ROOT_DIR/.local/codex-app-server.pid"
LAUNCH_LABEL="com.hiroki.ai-tutor.codex-app-server"
LAUNCH_DOMAIN="gui/$(id -u)"

launchctl bootout "$LAUNCH_DOMAIN/$LAUNCH_LABEL" >/dev/null 2>&1 || true
rm -f "$PID_FILE"
echo "Codex app-serverを停止しました。"
