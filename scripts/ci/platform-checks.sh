#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python_bin="${PYTHON_BIN:-python3}"

"$python_bin" - <<'PY'
import sys

if sys.version_info[:2] != (3, 12):
    raise SystemExit(f"Python 3.12 is required; found {sys.version.split()[0]}")
PY

node -e 'const major = Number(process.versions.node.split(".")[0]); if (major < 22) throw new Error(`Node.js 22+ is required; found ${process.version}`);'

runtime_root="$(mktemp -d /tmp/gogainen-platform-checks.XXXXXX)"
python_env="$runtime_root/venv"
pytest_tmp="$runtime_root/pytest"
mkdir -p "$pytest_tmp"
cleanup() {
  rm -rf "$runtime_root"
}
trap cleanup EXIT

"$python_bin" -m venv "$python_env"
"$python_env/bin/python" -m pip install --disable-pip-version-check -r "$repo_root/backend/requirements.txt"

(
  cd "$repo_root/backend"
  AI_BACKEND=mock "$python_env/bin/python" -m pytest -q --basetemp="$pytest_tmp"
)

(
  cd "$repo_root/frontend"
  npm ci
  npm test
)

PYTHON_BIN="$python_env/bin/python" bash "$repo_root/scripts/ci/compose-socket-smoke.sh" "$repo_root"
