#!/usr/bin/env bash
# V6 BFF 常驻（platform-v6 :3001 依赖此进程）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.
export BFF_PORT="${BFF_PORT:-8788}"
export BFF_HOST="${BFF_HOST:-127.0.0.1}"
PY="${PYTHON:-}"
if [[ -z "$PY" && -x "/Users/corrine/miniconda3/bin/python3" ]]; then
  PY="/Users/corrine/miniconda3/bin/python3"
fi
PY="${PY:-python3}"
echo "Starting V6 BFF on http://${BFF_HOST}:${BFF_PORT} (Ctrl+C to stop)"
exec "$PY" -m src.main run-bff
