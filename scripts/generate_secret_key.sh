#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/python ]]; then
  echo "Missing .venv. Run scripts/setup_venv.sh first." >&2
  exit 1
fi

.venv/bin/python - <<'PY'
from cryptography.fernet import Fernet

print(Fernet.generate_key().decode())
PY
