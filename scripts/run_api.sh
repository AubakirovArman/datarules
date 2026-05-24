#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/python ]]; then
  echo "Missing .venv. Run scripts/setup_venv.sh first." >&2
  exit 1
fi

set -a
[[ -f .env ]] && source .env
if [[ -z "${DATARULES_SECRET_KEY:-}" ]]; then
  scripts/ensure_runtime_env.sh
  runtime_env="${DATARULES_RUNTIME_ENV:-storage/runtime.env}"
  [[ -f "$runtime_env" ]] && source "$runtime_env"
fi
set +a

HOST="${API_HOST:-0.0.0.0}"
PORT="${API_PORT:-8017}"
PYTHONPATH=backend .venv/bin/python -m uvicorn datarules_api.main:app --host "$HOST" --port "$PORT"
