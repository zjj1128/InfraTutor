#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backend_pid=""
frontend_pid=""

cleanup() {
  if [[ -n "$backend_pid" ]]; then
    kill "$backend_pid" 2>/dev/null || true
  fi
  if [[ -n "$frontend_pid" ]]; then
    kill "$frontend_pid" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

cd "$project_root"

if [[ ! -x ".venv/bin/python" || ! -d "frontend/node_modules" ]]; then
  echo "依赖尚未安装，请先运行 make setup。" >&2
  exit 1
fi

.venv/bin/python -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000 &
backend_pid=$!

npm --prefix frontend run dev &
frontend_pid=$!

wait -n "$backend_pid" "$frontend_pid"
