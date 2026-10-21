#!/usr/bin/env sh

set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ENV_FILE="$ROOT_DIR/.env"

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi

LISTEN_URL="${CODEX_APP_SERVER_LISTEN_URL:-ws://127.0.0.1:4500}"
case "${1:-}" in
  --docker)
    # A socket bind mount works across WSL and Docker without exposing a TCP port.
    SOCKET_DIR="$ROOT_DIR/.local/codex-app-server"
    mkdir -p "$SOCKET_DIR"
    chmod 700 "$SOCKET_DIR"
    LISTEN_URL="unix://$SOCKET_DIR/server.sock"
    ;;
  "") ;;
  *)
    printf 'Usage: %s [--docker]\n' "$0" >&2
    exit 2
    ;;
esac
exec codex app-server --listen "$LISTEN_URL"
