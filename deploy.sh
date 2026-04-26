#!/usr/bin/env bash
# deploy.sh — push to GitHub and deploy AI Market to the EC2 instance.
#
# Usage:
#   ./deploy.sh                       # push current commit, then deploy
#   ./deploy.sh "commit message"      # stage + commit all changes, push, deploy
#   ./deploy.sh --skip-push           # only redeploy what's already on origin
#   ./deploy.sh --logs                # tail uvicorn logs after deploy (Ctrl+C to stop)
#   ./deploy.sh -h | --help
#
# Env overrides (all optional):
#   DEPLOY_HOST   (default: 98.84.157.50)
#   DEPLOY_USER   (default: ec2-user)
#   DEPLOY_KEY    (default: ~/Downloads/ai-market-key.pem)
#   DEPLOY_PATH   (default: ~/AI-market)
#   BRANCH        (default: main)

set -euo pipefail

# ── Config ──────────────────────────────────────────────────
DEPLOY_HOST="${DEPLOY_HOST:-98.84.157.50}"
DEPLOY_USER="${DEPLOY_USER:-ec2-user}"
DEPLOY_KEY="${DEPLOY_KEY:-$HOME/Downloads/ai-market-key.pem}"
DEPLOY_PATH="${DEPLOY_PATH:-~/AI-market}"
BRANCH="${BRANCH:-main}"

# ── Colors ──────────────────────────────────────────────────
if [[ -t 1 ]]; then
  GREEN="\033[32m"; YELLOW="\033[33m"; RED="\033[31m"; BLUE="\033[34m"; DIM="\033[2m"; RESET="\033[0m"
else
  GREEN=""; YELLOW=""; RED=""; BLUE=""; DIM=""; RESET=""
fi
ok()   { printf "${GREEN}✓${RESET} %s\n" "$*"; }
info() { printf "${BLUE}→${RESET} %s\n" "$*"; }
warn() { printf "${YELLOW}!${RESET} %s\n" "$*"; }
die()  { printf "${RED}✗${RESET} %s\n" "$*" >&2; exit 1; }
hr()   { printf "${DIM}%s${RESET}\n" "────────────────────────────────────────────────────────"; }

# ── Help ────────────────────────────────────────────────────
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  sed -n '2,17p' "$0" | sed -E 's/^# ?//'
  exit 0
fi

# ── Flag parsing ─────────────────────────────────────────────
SKIP_PUSH=0
TAIL_LOGS=0
COMMIT_MSG=""
for arg in "$@"; do
  case "$arg" in
    --skip-push) SKIP_PUSH=1 ;;
    --logs)      TAIL_LOGS=1 ;;
    -*)          die "Unknown flag: $arg" ;;
    *)           COMMIT_MSG="$arg" ;;
  esac
done

# ── Always run from the repo root ────────────────────────────
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# ── Pre-flight ───────────────────────────────────────────────
[[ -f "$DEPLOY_KEY" ]] || die "SSH key not found: $DEPLOY_KEY"
chmod 400 "$DEPLOY_KEY" 2>/dev/null || true
command -v git >/dev/null || die "git is not installed"
command -v ssh >/dev/null || die "ssh is not installed"
git rev-parse --git-dir >/dev/null 2>&1 || die "Not a git repo: $ROOT"

# ── Step 1: handle local changes ─────────────────────────────
hr
# Check both modified-tracked AND untracked files
has_changes=0
if ! git diff --quiet || ! git diff --cached --quiet; then has_changes=1; fi
if [[ -n "$(git ls-files --others --exclude-standard)" ]]; then has_changes=1; fi

if (( has_changes )); then
  if [[ -n "$COMMIT_MSG" ]]; then
    info "Staging all changes..."
    git add -A
    info "Committing: $COMMIT_MSG"
    git commit -m "$COMMIT_MSG"
    ok "Committed"
  else
    warn "You have uncommitted changes. Either commit them first, or pass a message:"
    warn "  ./deploy.sh \"my commit message\""
    git status --short
    die "Aborting."
  fi
elif [[ -n "$COMMIT_MSG" ]]; then
  warn "Nothing to commit but you provided a message — skipping commit."
fi

# ── Step 2: push (unless --skip-push) ────────────────────────
hr
if (( SKIP_PUSH )); then
  warn "--skip-push set — not pushing to origin"
else
  local_sha=$(git rev-parse HEAD)
  if remote_sha=$(git ls-remote origin "$BRANCH" 2>/dev/null | awk '{print $1}'); then
    if [[ "$local_sha" != "$remote_sha" ]]; then
      info "Pushing $BRANCH to origin..."
      git push origin "$BRANCH"
      ok "Pushed: ${local_sha:0:10}"
    else
      info "Already up to date with origin/$BRANCH"
    fi
  else
    warn "Couldn't query origin/$BRANCH — pushing anyway"
    git push origin "$BRANCH"
  fi
fi

# ── Step 3: SSH + pull + rebuild + restart ───────────────────
hr
SSH_OPTS=(-i "$DEPLOY_KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10)
SSH_CMD=(ssh "${SSH_OPTS[@]}" "$DEPLOY_USER@$DEPLOY_HOST")

info "Connecting to $DEPLOY_USER@$DEPLOY_HOST ..."
"${SSH_CMD[@]}" "echo connected" >/dev/null || die "SSH failed"
ok "SSH connected"

info "Pulling on EC2..."
"${SSH_CMD[@]}" "cd $DEPLOY_PATH && git pull origin $BRANCH" || die "git pull failed on EC2"

info "Rebuilding docker image (this is the slow step ~30-60s)..."
"${SSH_CMD[@]}" "cd $DEPLOY_PATH && docker compose build app 2>&1 | tail -8" || die "docker build failed"

info "Restarting container..."
"${SSH_CMD[@]}" "cd $DEPLOY_PATH && docker compose up -d" || die "docker compose up failed"

info "Waiting for healthcheck..."
sleep 5

info "Container status + smoke test:"
"${SSH_CMD[@]}" "cd $DEPLOY_PATH && docker compose ps && \
  curl -s -o /dev/null -w 'GET /api/dashboard  → HTTP %{http_code} in %{time_total}s\n' http://localhost:8000/api/dashboard && \
  curl -s -o /dev/null -w 'GET /api/trade-feed → HTTP %{http_code} in %{time_total}s\n' http://localhost:8000/api/trade-feed?limit=5"

hr
ok "Deployed: http://$DEPLOY_HOST:8000"

# ── Step 4: optional log tail ────────────────────────────────
if (( TAIL_LOGS )); then
  hr
  info "Tailing uvicorn logs (Ctrl+C to stop)..."
  "${SSH_CMD[@]}" "cd $DEPLOY_PATH && docker compose logs -f --tail=50 app"
fi
