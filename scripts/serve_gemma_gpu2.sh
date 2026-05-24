#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/python ]]; then
  echo "Missing .venv. Run scripts/setup_venv.sh first." >&2
  exit 1
fi

if ! .venv/bin/python -c "import vllm" >/dev/null 2>&1; then
  echo "vLLM is not installed in .venv. Run scripts/install_vllm.sh first." >&2
  exit 1
fi

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-2}"
MODEL_DIR="${GEMMA_MODEL_ID:-/mnt/hf_model_weights/arman/3bit/models/google-gemma-4-31B-it}"
PORT="${GEMMA_PORT:-8018}"
MAX_MODEL_LEN="${VLLM_MAX_MODEL_LEN:-65536}"

.venv/bin/python -m vllm.entrypoints.openai.api_server \
  --host 0.0.0.0 \
  --port "$PORT" \
  --model "$MODEL_DIR" \
  --served-model-name "$MODEL_DIR" \
  --dtype bfloat16 \
  --max-model-len "$MAX_MODEL_LEN"
