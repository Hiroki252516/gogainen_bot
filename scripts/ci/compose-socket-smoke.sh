#!/usr/bin/env bash
set -euo pipefail

repo_root="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
python_bin="${PYTHON_BIN:-$repo_root/backend/.venv/bin/python}"

if ! command -v docker >/dev/null 2>&1; then
  printf 'Docker CLI is required for the Compose smoke test.\n' >&2
  exit 1
fi
docker info >/dev/null
docker compose version

runtime_base="$repo_root/.local"
mkdir -p "$runtime_base"
smoke_root="$(mktemp -d "$runtime_base/gogainen-compose-smoke.XXXXXX")"
chmod 755 "$smoke_root"
socket_path="$smoke_root/.local/codex-app-server/server.sock"
env_file="$smoke_root/ci.env"
tcp_port_file="$smoke_root/fake-app-server-port"
compose_args=()
compose_started=0
fake_server_pid=""
server_logs=()

cleanup() {
  result=$?
  set +e
  if [ "$result" -ne 0 ] && [ "${#compose_args[@]}" -gt 0 ] && [ "$compose_started" -eq 1 ]; then
    printf '\n--- Compose logs ---\n'
    "${compose_args[@]}" logs --no-color
  fi
  if [ "${#compose_args[@]}" -gt 0 ] && [ "$compose_started" -eq 1 ]; then
    "${compose_args[@]}" down --volumes --remove-orphans
  fi
  if [ -n "$fake_server_pid" ]; then
    kill "$fake_server_pid" 2>/dev/null
    wait "$fake_server_pid" 2>/dev/null
  fi
  for log in "${server_logs[@]}"; do
    if [ "$result" -ne 0 ]; then
      printf '\n--- fake app-server log: %s ---\n' "$log"
      cat "$log" 2>/dev/null
    fi
  done
  rm -rf "$smoke_root"
  exit "$result"
}
trap cleanup EXIT

mkdir -p "$smoke_root/.local/codex-app-server"
mkdir -p "$smoke_root/scripts"
chmod +x "$repo_root/scripts/ci/codex"
chmod 700 "$smoke_root/.local/codex-app-server"
ln -s "$repo_root/scripts/start-codex-app-server.sh" "$smoke_root/scripts/start-codex-app-server.sh"
for path in backend frontend rag_agent_knowledge_base 'rag_ready_教材'; do
  ln -s "$repo_root/$path" "$smoke_root/$path"
done

for key in APP_ENV BACKEND_NETWORK_MODE DATABASE_URL AI_BACKEND CODEX_APP_SERVER_URL \
  CODEX_WS_TOKEN_FILE CODEX_APP_SERVER_CWD CODEX_TURN_TIMEOUT_SEC CODEX_MODEL \
  CODEX_REASONING_EFFORT RAG_BASE_DIR MAX_LEARNING_TARGETS MAX_TURNS_PER_TERM \
  EXPORT_DIR FRONTEND_ORIGIN FRONTEND_PORT POSTGRES_USER POSTGRES_PASSWORD \
  POSTGRES_DB POSTGRES_PORT FRONTEND_INTERNAL_API_BASE_URL NEXT_PUBLIC_API_BASE_URL \
  IDENTITY_MAPPING_PATH; do
  unset "$key" || true
done

frontend_port="$("$python_bin" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
read -r -a connection_modes <<<"${CI_APP_SERVER_MODES:-file directory}"
for connection_mode in "${connection_modes[@]}"; do
  case "$connection_mode" in
    file|directory|tcp) ;;
    *) printf 'Unsupported CI app-server mode: %s\n' "$connection_mode" >&2; exit 2 ;;
  esac
done

start_fake_app_server() {
  local connection_mode="$1"
  local listen_url=""
  local server_log="$smoke_root/fake-app-server-${connection_mode}.log"
  local launch_args=("")

  server_logs+=("$server_log")
  if [ "$connection_mode" = unix ]; then
    if [ -e "$socket_path" ]; then unlink "$socket_path"; fi
    listen_url="unix://$socket_path"
    launch_args=(--docker)
  else
    : >"$tcp_port_file"
    listen_url="ws://0.0.0.0:0"
  fi

  CI_FAKE_APP_SERVER_MODE="$connection_mode" \
    CI_FAKE_APP_SERVER_SCRIPT="$repo_root/scripts/ci/fake_codex_app_server.py" \
    CI_FAKE_APP_SERVER_PORT_FILE="$tcp_port_file" \
    CI_PYTHON_BIN="$python_bin" \
    PATH="$repo_root/scripts/ci:$PATH" \
    CODEX_APP_SERVER_LISTEN_URL="$listen_url" \
    bash "$smoke_root/scripts/start-codex-app-server.sh" "${launch_args[@]}" >"$server_log" 2>&1 &
  fake_server_pid=$!

  for attempt in $(seq 1 100); do
    if [ "$connection_mode" = unix ] && [ -S "$socket_path" ]; then return 0; fi
    if [ "$connection_mode" = tcp ] && [ -s "$tcp_port_file" ]; then
      tcp_port="$(<"$tcp_port_file")"
      return 0
    fi
    if ! kill -0 "$fake_server_pid" 2>/dev/null; then cat "$server_log" >&2; return 1; fi
    sleep 0.1
  done

  printf 'Fake app-server did not become ready for %s mode.\n' "$connection_mode" >&2
  return 1
}

stop_fake_app_server() {
  if [ -n "$fake_server_pid" ]; then
    kill "$fake_server_pid" 2>/dev/null || true
    wait "$fake_server_pid" 2>/dev/null || true
    fake_server_pid=""
  fi
}

write_env_file() {
  local app_server_url="$1"
  cat >"$env_file" <<EOF
APP_ENV=ci
BACKEND_NETWORK_MODE=bridge
DATABASE_URL=postgresql+psycopg://app:app@db:5432/ai_tutor
AI_BACKEND=codex_app_server
CODEX_APP_SERVER_URL=${app_server_url}
CODEX_WS_TOKEN_FILE=
CODEX_APP_SERVER_CWD=/tmp
CODEX_TURN_TIMEOUT_SEC=5
CODEX_MODEL=gpt-5.6-luna
CODEX_REASONING_EFFORT=low
RAG_BASE_DIR=/rag_agent_knowledge_base
MAX_LEARNING_TARGETS=3
MAX_TURNS_PER_TERM=3
EXPORT_DIR=/app/exports
FRONTEND_ORIGIN=http://127.0.0.1:${frontend_port}
FRONTEND_PORT=${frontend_port}
POSTGRES_USER=app
POSTGRES_PASSWORD=app
POSTGRES_DB=ai_tutor
POSTGRES_PORT=5432
FRONTEND_INTERNAL_API_BASE_URL=http://backend:8000
NEXT_PUBLIC_API_BASE_URL=
IDENTITY_MAPPING_PATH=/identity-mappings/mappings.sqlite3
EOF
}

frontend_port_url="http://127.0.0.1:${frontend_port}"
project_name="gogainen-compose-ci-${GITHUB_RUN_ID:-local}-$$"

report_mode_failure() {
  local connection_mode="$1"
  printf 'App-server connection mode failed: %s\n' "$connection_mode" >&2
  if [ "$compose_started" -eq 1 ]; then
    printf '\n--- Compose logs for %s ---\n' "$connection_mode" >&2
    "${compose_args[@]}" logs --no-color >&2 || true
    "${compose_args[@]}" down --volumes --remove-orphans >&2 || true
    compose_started=0
  fi
}

run_connection_mode() {
  local connection_mode="$1"
  local override_file=""
  local container_socket_path=""
  local app_server_url=""
  local health=""
  local ai_status=""
  local reachable=0

  case "$connection_mode" in
    file)
      override_file="$repo_root/docker-compose.override.example.yml"
      container_socket_path=/codex-app-server.sock
      app_server_url=unix:///tmp/overridden-by-local-compose-file.sock
      ;;
    directory)
      override_file="$repo_root/docker-compose.override.directory-mount.example.yml"
      container_socket_path=/codex-app-server/server.sock
      app_server_url=unix:///tmp/overridden-by-local-compose-file.sock
      ;;
    tcp)
      app_server_url="ws://host.docker.internal:${tcp_port}"
      ;;
    *)
      printf 'Unsupported CI app-server mode: %s\n' "$connection_mode" >&2
      return 1
      ;;
  esac

  write_env_file "$app_server_url"
  compose_args=(
    docker compose
    --project-name "$project_name"
    --project-directory "$smoke_root"
    --env-file "$env_file"
    -f "$repo_root/docker-compose.yml"
  )
  if [ -n "$override_file" ]; then compose_args+=(-f "$override_file"); fi
  compose_args+=(-f "$repo_root/docker-compose.ci.yml")

  printf '\nTesting %s app-server connection with Docker Compose...\n' "$connection_mode"
  if ! "${compose_args[@]}" config --quiet; then report_mode_failure "$connection_mode"; return 1; fi
  compose_started=1
  if ! "${compose_args[@]}" up --build --detach --wait --wait-timeout 360; then
    report_mode_failure "$connection_mode"
    return 1
  fi

  if [ -n "$container_socket_path" ] && ! "${compose_args[@]}" exec -T backend python -c \
    'import os,stat,sys; p=sys.argv[1]; parent=os.path.dirname(p); exists=os.path.exists(p); is_socket=exists and stat.S_ISSOCK(os.stat(p).st_mode); print({"socket_path":p,"exists":exists,"is_socket":is_socket,"parent_entries":os.listdir(parent) if os.path.isdir(parent) else None}); assert is_socket, f"not a Unix socket in backend container: {p}"' \
    "$container_socket_path"; then
    report_mode_failure "$connection_mode"
    return 1
  fi

  for attempt in $(seq 1 60); do
    if curl --fail --silent --show-error "$frontend_port_url/" --output /dev/null; then reachable=1; break; fi
    sleep 2
  done
  if [ "$reachable" -ne 1 ]; then report_mode_failure "$connection_mode"; return 1; fi

  if ! health="$(curl --fail --silent --show-error "$frontend_port_url/api/health")" || \
    ! printf '%s' "$health" | "$python_bin" -c 'import json,sys; assert json.load(sys.stdin).get("status") == "ok"'; then
    report_mode_failure "$connection_mode"
    return 1
  fi
  if ! ai_status="$(curl --fail --silent --show-error "$frontend_port_url/api/admin/ai/status")" || \
    ! printf '%s' "$ai_status" | "$python_bin" -c '
import json, sys
status = json.load(sys.stdin)
assert status.get("ai_backend") == "codex_app_server", status
assert status.get("app_server_reachable") is True, status
assert status.get("logged_in") is False, status
'; then
    report_mode_failure "$connection_mode"
    return 1
  fi

  printf 'The %s connection reached the unauthenticated fake app-server; web and API are healthy.\n' "$connection_mode"
  if ! "${compose_args[@]}" down --volumes --remove-orphans; then
    compose_started=0
    return 1
  fi
  compose_started=0
}

failed_modes=()
for connection_mode in "${connection_modes[@]}"; do
  server_mode="$connection_mode"
  if [ "$connection_mode" = file ] || [ "$connection_mode" = directory ]; then server_mode=unix; fi
  if ! start_fake_app_server "$server_mode"; then
    failed_modes+=("$connection_mode")
    stop_fake_app_server
    continue
  fi
  if ! run_connection_mode "$connection_mode"; then
    failed_modes+=("$connection_mode")
  fi
  stop_fake_app_server
done

if [ "${#failed_modes[@]}" -gt 0 ]; then
  printf 'Failed app-server connection mode(s): %s\n' "${failed_modes[*]}" >&2
  exit 1
fi

printf 'Docker Compose app-server and web startup smoke tests passed.\n'
