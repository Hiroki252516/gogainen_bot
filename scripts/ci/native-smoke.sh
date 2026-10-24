#!/usr/bin/env bash
set -euo pipefail

repo_root="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
smoke_dir="$(mktemp -d /tmp/gogainen-smoke.XXXXXX)"
backend_port="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
frontend_port="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
backend_pid=""
frontend_pid=""

cleanup() {
  result=$?
  if [ "$result" -ne 0 ]; then
    printf '\n--- backend log ---\n'
    tail -n 120 "$smoke_dir/backend.log" 2>/dev/null || true
    printf '\n--- frontend log ---\n'
    tail -n 120 "$smoke_dir/frontend.log" 2>/dev/null || true
  fi
  if [ -n "$frontend_pid" ]; then
    kill "$frontend_pid" 2>/dev/null || true
    wait "$frontend_pid" 2>/dev/null || true
  fi
  if [ -n "$backend_pid" ]; then
    kill "$backend_pid" 2>/dev/null || true
    wait "$backend_pid" 2>/dev/null || true
  fi
  rm -rf "$smoke_dir"
  exit "$result"
}
trap cleanup EXIT

export APP_ENV=ci
export DATABASE_URL="sqlite:////${smoke_dir#/}/app.db"
export AI_BACKEND=mock
export CODEX_APP_SERVER_URL="unix://$smoke_dir/unused-codex-app-server.sock"
export CODEX_WS_TOKEN_FILE=""
export CODEX_APP_SERVER_CWD="$smoke_dir"
export CODEX_TURN_TIMEOUT_SEC=5
export CODEX_MODEL=gpt-5.6-luna
export CODEX_REASONING_EFFORT=low
export RAG_BASE_DIR="$repo_root/rag_agent_knowledge_base"
export MAX_LEARNING_TARGETS=3
export MAX_TURNS_PER_TERM=3
export EXPORT_DIR="$smoke_dir/exports"
export IDENTITY_MAPPING_PATH="$smoke_dir/identity-mappings.sqlite3"
export FRONTEND_ORIGIN="http://127.0.0.1:$frontend_port"
export NEXT_PUBLIC_API_BASE_URL=""

(
  cd "$repo_root/backend"
  exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$backend_port"
) >"$smoke_dir/backend.log" 2>&1 &
backend_pid=$!

(
  cd "$repo_root/frontend"
  INTERNAL_API_BASE_URL="http://127.0.0.1:$backend_port" npm run build
) >"$smoke_dir/frontend-build.log" 2>&1 || {
  cat "$smoke_dir/frontend-build.log"
  exit 1
}

(
  cd "$repo_root/frontend"
  exec ./node_modules/.bin/next start --hostname 127.0.0.1 --port "$frontend_port"
) >"$smoke_dir/frontend.log" 2>&1 &
frontend_pid=$!

wait_for_url() {
  url="$1"
  label="$2"
  for attempt in $(seq 1 90); do
    if curl --fail --silent --show-error "$url" --output "$smoke_dir/response" 2>/dev/null; then
      printf '%s is ready\n' "$label"
      return 0
    fi
    sleep 2
  done
  printf 'Timed out waiting for %s at %s\n' "$label" "$url" >&2
  return 1
}

wait_for_url "http://127.0.0.1:$backend_port/api/health" "backend"
grep -q '"status":"ok"' "$smoke_dir/response"
wait_for_url "http://127.0.0.1:$frontend_port/" "frontend"
wait_for_url "http://127.0.0.1:$frontend_port/api/health" "frontend API proxy"
grep -q '"status":"ok"' "$smoke_dir/response"

ai_status="$(curl --fail --silent --show-error "http://127.0.0.1:$frontend_port/api/admin/ai/status")"
printf '%s' "$ai_status" | node -e '
let body = "";
process.stdin.on("data", chunk => body += chunk);
process.stdin.on("end", () => {
  const status = JSON.parse(body);
  if (status.ai_backend !== "mock" || status.app_server_reachable !== null || status.logged_in !== null) {
    throw new Error(`Unexpected CI AI status: ${body}`);
  }
});
'

printf 'Native web startup smoke test passed (backend=%s, frontend=%s).\n' "$backend_port" "$frontend_port"
