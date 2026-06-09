#!/usr/bin/env bash
# platform-v6 开发：先确保 V6 BFF :8788 在线，再启动 Next :3001
set -euo pipefail

PLATFORM_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
V6_ROOT="$(cd "$PLATFORM_ROOT/../V6" && pwd)"
BFF_PORT="${BFF_PORT:-8788}"
BFF_HOST="${BFF_HOST:-127.0.0.1}"
BFF_URL="http://${BFF_HOST}:${BFF_PORT}"
STARTED_BFF_PID=""

resolve_python() {
  if [[ -n "${PYTHON:-}" && -x "${PYTHON}" ]]; then
    echo "$PYTHON"
    return
  fi
  if [[ -x "/Users/corrine/miniconda3/bin/python3" ]]; then
    echo "/Users/corrine/miniconda3/bin/python3"
    return
  fi
  command -v python3
}

bff_healthy() {
  curl -sf -m 2 "${BFF_URL}/health" >/dev/null 2>&1
}

start_bff() {
  local py
  py="$(resolve_python)"
  if [[ -z "$py" ]]; then
    echo "错误：未找到 python3，无法启动 V6 BFF" >&2
    exit 1
  fi
  if [[ ! -d "$V6_ROOT/src" ]]; then
    echo "错误：未找到 V6 目录 $V6_ROOT" >&2
    exit 1
  fi
  echo ">> 启动 V6 BFF ${BFF_URL} ..."
  (
    cd "$V6_ROOT"
    export PYTHONPATH=.
    export BFF_PORT BFF_HOST
    exec "$py" -m src.main run-bff
  ) &
  STARTED_BFF_PID=$!
  for _ in $(seq 1 45); do
    if bff_healthy; then
      echo ">> BFF 已就绪 (pid ${STARTED_BFF_PID})"
      return 0
    fi
    if ! kill -0 "$STARTED_BFF_PID" 2>/dev/null; then
      echo "错误：BFF 进程异常退出，请查看 V6/data/bff_restart.log" >&2
      exit 1
    fi
    sleep 1
  done
  echo "错误：BFF 45s 内未响应 ${BFF_URL}/health" >&2
  exit 1
}

cleanup() {
  if [[ "${KEEP_BFF_ON_EXIT:-}" == "1" ]]; then
    return
  fi
  if [[ -n "$STARTED_BFF_PID" ]] && kill -0 "$STARTED_BFF_PID" 2>/dev/null; then
    echo ">> 停止 BFF (pid ${STARTED_BFF_PID})"
    kill "$STARTED_BFF_PID" 2>/dev/null || true
    wait "$STARTED_BFF_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

port_busy() {
  lsof -ti ":$1" >/dev/null 2>&1
}

if port_busy 3001; then
  echo "错误：端口 3001 已被占用。请先结束旧的前端进程，或执行: lsof -ti :3001 | xargs kill" >&2
  KEEP_BFF_ON_EXIT=1
  exit 1
fi

if bff_healthy; then
  echo ">> BFF 已在运行 ${BFF_URL}"
else
  start_bff
fi

cd "$PLATFORM_ROOT"
export BFF_BASE_URL="${BFF_URL}"
echo ">> 启动 platform-v6 http://localhost:3001 (BFF → ${BFF_URL})"
exec npx next dev --webpack -p 3001
