#!/usr/bin/env bash
set -euo pipefail

windows_checkout="${1:?Pass the Windows checkout path converted with wslpath.}"
runtime_root="$(mktemp -d "$HOME/gogainen-wsl-ci.XXXXXX")"
repo_root="$runtime_root/repository"

cleanup() {
  result=$?
  set +e
  rm -rf "$runtime_root"
  exit "$result"
}
trap cleanup EXIT

if [ "$(id -u)" -eq 0 ]; then
  printf 'Configure a non-root default WSL user and run the CI checks as that user.\n' >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  printf 'Docker CLI is unavailable in WSL. Enable Docker Desktop WSL integration for Ubuntu-24.04.\n' >&2
  exit 1
fi
server_os="$(docker info --format '{{.OperatingSystem}}')"
if [[ "$server_os" != *"Docker Desktop"* ]]; then
  printf 'Expected the Docker Desktop daemon through WSL integration; found: %s\n' "$server_os" >&2
  exit 1
fi
docker compose version

python3.12 - <<'PY'
import sys

if sys.version_info[:2] != (3, 12):
    raise SystemExit(f"Python 3.12 is required; found {sys.version.split()[0]}")
PY
python3.12 -m venv "$runtime_root/preflight-venv"
node -e 'const major = Number(process.versions.node.split(".")[0]); if (major < 22) throw new Error(`Node.js 22+ is required; found ${process.version}`);'
npm --version
command -v curl >/dev/null 2>&1 || { printf 'curl is required for the web/API smoke test.\n' >&2; exit 1; }

mkdir -p "$repo_root"
cp -a "$windows_checkout/." "$repo_root/"
cd "$repo_root"
chmod +x scripts/ci/codex

printf 'WSL kernel: %s\n' "$(uname -r)"
printf 'Docker Desktop daemon: %s\n' "$server_os"

PYTHON_BIN=python3.12 bash scripts/ci/platform-checks.sh
