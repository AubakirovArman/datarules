#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/frontend"

set -a
[[ -f ../.env ]] && source ../.env
set +a

npm run dev -- --port "${FRONTEND_PORT:-5177}"
