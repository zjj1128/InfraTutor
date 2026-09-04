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

if ! runtime_output="$(.venv/bin/python -m backend.app.core.dev_info)"; then
  exit 1
fi
mapfile -t runtime <<< "$runtime_output"
backend_host="${runtime[0]}"
backend_port="${runtime[1]}"
frontend_host="${runtime[2]}"
frontend_port="${runtime[3]}"
llm_mode="${runtime[4]}"
active_seed="${runtime[5]}"

frontend_display_host="$frontend_host"
backend_display_host="$backend_host"
if [[ "$frontend_display_host" == "0.0.0.0" ]]; then frontend_display_host="127.0.0.1"; fi
if [[ "$backend_display_host" == "0.0.0.0" ]]; then backend_display_host="127.0.0.1"; fi

echo "Frontend URL: http://${frontend_display_host}:${frontend_port}"
echo "Backend URL:  http://${backend_display_host}:${backend_port}"
echo "LLM mode:     ${llm_mode}"
echo "Database seed: ${active_seed}"

.venv/bin/python -m uvicorn backend.app.main:app --reload --host "$backend_host" --port "$backend_port" &
backend_pid=$!

BACKEND_HOST="$backend_host" BACKEND_PORT="$backend_port" \
  FRONTEND_HOST="$frontend_host" FRONTEND_PORT="$frontend_port" \
  npm --prefix frontend run dev &
frontend_pid=$!

wait -n "$backend_pid" "$frontend_pid"
