#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/样式文件"
ROOT_ENV_FILE="$ROOT_DIR/.env"
ROOT_ENV_EXAMPLE="$ROOT_DIR/.env.example"
BACKEND_ENV_FILE="$BACKEND_DIR/.env"
BACKEND_ENV_EXAMPLE="$BACKEND_DIR/.env.example"
ROOT_VENV_DIR="$ROOT_DIR/.venv"
RUN_DEV_SCRIPT="$ROOT_DIR/run-dev.sh"

PYTHON_BIN=""
PIP_BIN=""

log() {
  echo "[run-full] $*"
}

fail() {
  echo "[run-full] $*" >&2
  exit 1
}

copy_if_missing() {
  local target=$1
  local source=$2
  if [[ -f "$target" || ! -f "$source" ]]; then
    return
  fi
  cp "$source" "$target"
  log "Created $(basename "$target") from $(basename "$source")"
}

ensure_env_files() {
  copy_if_missing "$ROOT_ENV_FILE" "$ROOT_ENV_EXAMPLE"
  copy_if_missing "$BACKEND_ENV_FILE" "$BACKEND_ENV_EXAMPLE"
}

ensure_python() {
  if [[ -x "$ROOT_VENV_DIR/bin/python" ]]; then
    PYTHON_BIN="$ROOT_VENV_DIR/bin/python"
    PIP_BIN="$ROOT_VENV_DIR/bin/pip"
    return
  fi

  if ! command -v python3 >/dev/null 2>&1; then
    fail "python3 not found. Install Python 3 first."
  fi

  log "Creating Python virtual environment at $ROOT_VENV_DIR"
  python3 -m venv "$ROOT_VENV_DIR"
  PYTHON_BIN="$ROOT_VENV_DIR/bin/python"
  PIP_BIN="$ROOT_VENV_DIR/bin/pip"
}

ensure_backend_dependencies() {
  if "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import importlib.util
required = ("fastapi", "uvicorn", "alembic", "redis", "chromadb", "psycopg")
missing = [name for name in required if importlib.util.find_spec(name) is None]
raise SystemExit(1 if missing else 0)
PY
  then
    return
  fi

  log "Installing backend dependencies"
  "$PIP_BIN" install -r "$BACKEND_DIR/requirements.txt"
}

ensure_frontend_dependencies() {
  if [[ -d "$FRONTEND_DIR/node_modules" ]]; then
    return
  fi

  if ! command -v npm >/dev/null 2>&1; then
    fail "npm not found. Install Node.js first."
  fi

  log "Installing frontend dependencies"
  (
    cd "$FRONTEND_DIR"
    npm install
  )
}

docker_app_path() {
  if [[ -d "/Applications/Docker.app" ]]; then
    echo "/Applications/Docker.app"
    return
  fi
  if [[ -d "$HOME/Applications/Docker.app" ]]; then
    echo "$HOME/Applications/Docker.app"
    return
  fi
  echo ""
}

ensure_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    fail "docker command not found. Install Docker Desktop first."
  fi

  if docker info >/dev/null 2>&1; then
    return
  fi

  local app_path
  app_path="$(docker_app_path)"
  if [[ -n "$app_path" ]] && command -v open >/dev/null 2>&1; then
    log "Starting Docker Desktop"
    open -a Docker >/dev/null 2>&1 || true
  fi

  for _ in $(seq 1 90); do
    if docker info >/dev/null 2>&1; then
      return
    fi
    sleep 2
  done

  fail "Docker daemon is not ready. Start Docker Desktop and rerun ./run-full.sh"
}

warn_optional_configuration() {
  local missing=()

  if ! grep -Eq '^WORKBOT_DINGTALK_APP_ID=.+' "$BACKEND_ENV_FILE"; then
    missing+=("WORKBOT_DINGTALK_APP_ID")
  fi
  if ! grep -Eq '^WORKBOT_DINGTALK_AGENT_ID=.+' "$BACKEND_ENV_FILE"; then
    missing+=("WORKBOT_DINGTALK_AGENT_ID")
  fi
  if ! grep -Eq '^WORKBOT_DINGTALK_CLIENT_ID=.+' "$BACKEND_ENV_FILE"; then
    missing+=("WORKBOT_DINGTALK_CLIENT_ID")
  fi
  if ! grep -Eq '^WORKBOT_DINGTALK_CLIENT_SECRET=.+' "$BACKEND_ENV_FILE"; then
    missing+=("WORKBOT_DINGTALK_CLIENT_SECRET")
  fi
  if ! grep -Eq '^WORKBOT_DINGTALK_CORP_ID=.+' "$BACKEND_ENV_FILE"; then
    missing+=("WORKBOT_DINGTALK_CORP_ID")
  fi

  if (( ${#missing[@]} > 0 )); then
    log "Warning: DingTalk real integration is still missing config: ${missing[*]}"
  fi
}

main() {
  ensure_env_files
  ensure_python
  ensure_backend_dependencies
  ensure_frontend_dependencies
  ensure_docker
  warn_optional_configuration

  if [[ ! -x "$RUN_DEV_SCRIPT" ]]; then
    fail "run-dev.sh is missing or not executable."
  fi

  export AUTO_START_INFRA=1
  exec "$RUN_DEV_SCRIPT"
}

main "$@"
