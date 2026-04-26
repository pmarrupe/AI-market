#!/usr/bin/env bash
# dev.sh — one-command local runner for AI Market (backend + frontend, LLM enabled).
#
# Usage:
#   ./dev.sh
#
# What it does:
#   1. Ensures .env exists, LLM_ENABLED=true, and LLM_API_KEY is set (prompts if empty).
#   2. Creates .venv and installs Python deps if missing.
#   3. Installs frontend npm deps if missing.
#   4. Starts uvicorn (127.0.0.1:8000, auto-reload) and Vite (localhost:5173).
#   5. Ctrl+C stops both cleanly.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

VENV="$ROOT/.venv"
ENV_FILE="$ROOT/.env"

# ── .env setup ──────────────────────────────────────────────────────
if [[ ! -f "$ENV_FILE" ]]; then
  cp .env.example "$ENV_FILE"
  echo "→ Created .env from .env.example"
fi

set_env_var() {
  # set_env_var KEY VALUE — in-place update or append to .env
  local key="$1" val="$2"
  if grep -q "^${key}=" "$ENV_FILE"; then
    # portable in-place sed (works on macOS BSD sed and GNU sed)
    sed -i.bak "s|^${key}=.*|${key}=${val}|" "$ENV_FILE" && rm -f "$ENV_FILE.bak"
  else
    printf '\n%s=%s\n' "$key" "$val" >> "$ENV_FILE"
  fi
}

get_env_var() {
  grep -E "^$1=" "$ENV_FILE" | head -n1 | cut -d= -f2- || true
}

set_env_var LLM_ENABLED true

if [[ -z "$(get_env_var LLM_API_KEY)" ]]; then
  echo
  echo "LLM_API_KEY is empty in .env."
  read -r -s -p "Paste your OpenAI-compatible API key (sk-...) and press Enter: " KEY
  echo
  if [[ -z "${KEY:-}" ]]; then
    echo "No key provided — aborting."
    exit 1
  fi
  set_env_var LLM_API_KEY "$KEY"
fi

# ── Python venv ─────────────────────────────────────────────────────
if [[ ! -x "$VENV/bin/python" ]]; then
  echo "→ Creating Python venv at $VENV"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --upgrade pip >/dev/null
  "$VENV/bin/pip" install -r requirements.txt
elif ! "$VENV/bin/python" -c "import uvicorn, fastapi" 2>/dev/null; then
  echo "→ Installing Python dependencies"
  "$VENV/bin/pip" install -r requirements.txt
fi

# ── Frontend deps ───────────────────────────────────────────────────
if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  echo "→ Installing frontend dependencies"
  (cd frontend && npm install)
fi

# ── Run both, clean up on exit ──────────────────────────────────────
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  trap - INT TERM EXIT
  echo
  echo "Stopping…"
  [[ -n "$BACKEND_PID"  ]] && kill "$BACKEND_PID"  2>/dev/null || true
  [[ -n "$FRONTEND_PID" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo
echo "→ Backend  : http://localhost:8000"
echo "→ Frontend : http://localhost:5173"
echo "Press Ctrl+C to stop both."
echo

"$VENV/bin/python" -m uvicorn app.main:app \
  --host 127.0.0.1 --port 8000 --reload &
BACKEND_PID=$!

(cd frontend && npm run dev) &
FRONTEND_PID=$!

wait
