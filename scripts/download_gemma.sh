#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/python ]]; then
  echo "Missing .venv. Run scripts/setup_venv.sh first." >&2
  exit 1
fi

MODEL_ID="${MODEL_ID:-google/gemma-4-31B-it}"
MODEL_DIR="${MODEL_DIR:-/mnt/hf_model_weights/arman/3bit/models/google-gemma-4-31B-it}"
export HF_HOME="${HF_HOME:-/mnt/hf_model_weights/arman/3bit/.hf_cache}"

.venv/bin/python - <<PY
from huggingface_hub import snapshot_download

path = snapshot_download(repo_id="$MODEL_ID", local_dir="$MODEL_DIR")
print(path)
PY
