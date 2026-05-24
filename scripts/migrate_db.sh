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
set +a

PYTHONPATH=backend .venv/bin/python -m alembic -c alembic.ini upgrade head
