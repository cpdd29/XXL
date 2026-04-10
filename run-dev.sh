#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/样式文件"
ROOT_VENV_DIR="$ROOT_DIR/.venv"
BACKEND_VENV_DIR="$BACKEND_DIR/.venv"
VENV_DIR=""
VENV_PYTHON=""
ALEMBIC_BIN=""
COMPOSE_ENV_FILE="$ROOT_DIR/.env"
COMPOSE_ENV_EXAMPLE="$ROOT_DIR/.env.example"
COMPOSE_CMD=(docker compose)
INFRA_SERVICES=(postgres redis nats chromadb)

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8080}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-http://${BACKEND_HOST}:${BACKEND_PORT}}"
NEXT_PUBLIC_WS_BASE_URL="${NEXT_PUBLIC_WS_BASE_URL:-ws://${BACKEND_HOST}:${BACKEND_PORT}}"
AUTO_START_INFRA="${AUTO_START_INFRA:-1}"
POSTGRES_DB="${POSTGRES_DB:-workbot}"
POSTGRES_USER="${POSTGRES_USER:-workbot}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-workbot}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
REDIS_PORT="${REDIS_PORT:-6379}"
NATS_PORT="${NATS_PORT:-4222}"
CHROMA_PORT="${CHROMA_PORT:-8000}"
FALLBACK_DATABASE_URL="${FALLBACK_DATABASE_URL:-sqlite:///./workbot-dev.sqlite3}"

WORKBOT_ENVIRONMENT="${WORKBOT_ENVIRONMENT:-development}"
WORKBOT_DATABASE_URL="${WORKBOT_DATABASE_URL:-postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:${POSTGRES_PORT}/${POSTGRES_DB}}"
WORKBOT_REDIS_URL="${WORKBOT_REDIS_URL:-redis://127.0.0.1:${REDIS_PORT}/0}"
WORKBOT_NATS_URL="${WORKBOT_NATS_URL:-nats://127.0.0.1:${NATS_PORT}}"
WORKBOT_CHROMA_URL="${WORKBOT_CHROMA_URL:-http://127.0.0.1:${CHROMA_PORT}}"
WORKBOT_CHROMA_CLIENT_MODE="${WORKBOT_CHROMA_CLIENT_MODE:-http}"
WORKBOT_CHROMA_PERSIST_PATH="${WORKBOT_CHROMA_PERSIST_PATH:-data/chroma}"
INFRA_MODE="docker"

BACKEND_PID=""
FRONTEND_PID=""

check_port_available() {
  local host=$1
  local port=$2
  local label=$3
  local pid=""

  pid="$(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null | head -n 1 || true)"
  if [[ -n "${pid}" ]]; then
    echo "${label} port ${port} is already in use by PID ${pid}."
    echo "Stop the existing process first, then rerun ./run-dev.sh"
    echo "If needed, you can inspect it with: lsof -i TCP:${port}"
    exit 1
  fi
}

ensure_compose_env_file() {
  if [[ -f "${COMPOSE_ENV_FILE}" || ! -f "${COMPOSE_ENV_EXAMPLE}" ]]; then
    return
  fi

  cp "${COMPOSE_ENV_EXAMPLE}" "${COMPOSE_ENV_FILE}"
  echo "Created ${COMPOSE_ENV_FILE} from .env.example"
}

wait_for_tcp_port() {
  local host=$1
  local port=$2
  local label=$3
  local retries="${4:-60}"
  local attempt=0

  while (( attempt < retries )); do
    if python3 - "$host" "$port" <<'PY' >/dev/null 2>&1
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.settimeout(1.0)
    try:
        sock.connect((host, port))
    except OSError:
        raise SystemExit(1)
raise SystemExit(0)
PY
    then
      return 0
    fi
    sleep 1
    attempt=$((attempt + 1))
  done

  echo "${label} did not become ready on ${host}:${port}."
  echo "Inspect containers with: docker compose ps && docker compose logs ${INFRA_SERVICES[*]}"
  exit 1
}

ensure_infra_services() {
  if [[ "${AUTO_START_INFRA}" != "1" ]]; then
    echo "Skipping dockerized infra because AUTO_START_INFRA=${AUTO_START_INFRA}"
    INFRA_MODE="fallback"
    return
  fi

  if ! command -v docker >/dev/null 2>&1; then
    echo "docker command not found. Falling back to local preview mode."
    INFRA_MODE="fallback"
    return
  fi

  if ! docker info >/dev/null 2>&1; then
    echo "Docker daemon is not running."
    echo "Falling back to local preview mode with SQLite and in-process degradation."
    INFRA_MODE="fallback"
    return
  fi

  ensure_compose_env_file

  echo "Starting infra services with docker compose: ${INFRA_SERVICES[*]}"
  (
    cd "${ROOT_DIR}"
    "${COMPOSE_CMD[@]}" up -d "${INFRA_SERVICES[@]}"
  )

  echo "Waiting for PostgreSQL on 127.0.0.1:${POSTGRES_PORT}"
  wait_for_tcp_port "127.0.0.1" "${POSTGRES_PORT}" "PostgreSQL"
  echo "Waiting for Redis on 127.0.0.1:${REDIS_PORT}"
  wait_for_tcp_port "127.0.0.1" "${REDIS_PORT}" "Redis"
  echo "Waiting for NATS on 127.0.0.1:${NATS_PORT}"
  wait_for_tcp_port "127.0.0.1" "${NATS_PORT}" "NATS"
  echo "Waiting for ChromaDB on 127.0.0.1:${CHROMA_PORT}"
  wait_for_tcp_port "127.0.0.1" "${CHROMA_PORT}" "ChromaDB"
}

cleanup() {
  local exit_code=$?

  trap - EXIT INT TERM

  if [[ -n "${BACKEND_PID}" ]] || [[ -n "${FRONTEND_PID}" ]]; then
    echo
    echo "Stopping dev servers..."
  fi

  if [[ -n "${BACKEND_PID}" ]] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
    kill "${BACKEND_PID}" 2>/dev/null || true
  fi

  if [[ -n "${FRONTEND_PID}" ]] && kill -0 "${FRONTEND_PID}" 2>/dev/null; then
    kill "${FRONTEND_PID}" 2>/dev/null || true
  fi

  if [[ -n "${BACKEND_PID}" ]]; then
    wait "${BACKEND_PID}" 2>/dev/null || true
  fi

  if [[ -n "${FRONTEND_PID}" ]]; then
    wait "${FRONTEND_PID}" 2>/dev/null || true
  fi

  exit "${exit_code}"
}

resolve_python_environment() {
  if [[ -x "${ROOT_VENV_DIR}/bin/python" ]]; then
    VENV_DIR="${ROOT_VENV_DIR}"
  elif [[ -x "${BACKEND_VENV_DIR}/bin/python" ]]; then
    VENV_DIR="${BACKEND_VENV_DIR}"
  else
    echo "Missing Python virtual environment."
    echo "Create one in either:"
    echo "  ${ROOT_VENV_DIR}"
    echo "  ${BACKEND_VENV_DIR}"
    echo "Example:"
    echo "  python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt"
    exit 1
  fi

  VENV_PYTHON="${VENV_DIR}/bin/python"
  ALEMBIC_BIN="${VENV_DIR}/bin/alembic"

  if [[ ! -x "${ALEMBIC_BIN}" ]]; then
    echo "Missing alembic in ${VENV_DIR}"
    echo "Install backend dependencies first with:"
    echo "  ${VENV_DIR}/bin/pip install -r backend/requirements.txt"
    exit 1
  fi
}

trap cleanup EXIT INT TERM

resolve_python_environment

if [[ ! -d "${FRONTEND_DIR}/node_modules" ]]; then
  echo "Missing frontend dependencies in ${FRONTEND_DIR}/node_modules"
  echo "Install them first with: cd 样式文件 && npm install"
  exit 1
fi

ensure_infra_services

check_port_available "${BACKEND_HOST}" "${BACKEND_PORT}" "Backend"
check_port_available "${FRONTEND_HOST}" "${FRONTEND_PORT}" "Frontend"

echo "Starting backend on http://${BACKEND_HOST}:${BACKEND_PORT}"
(
  cd "${BACKEND_DIR}"
  export WORKBOT_ENVIRONMENT
  if [[ "${INFRA_MODE}" == "docker" ]]; then
    export WORKBOT_DATABASE_URL
    export WORKBOT_CHROMA_CLIENT_MODE="http"
  else
    export WORKBOT_DATABASE_URL="${FALLBACK_DATABASE_URL}"
    export WORKBOT_CHROMA_CLIENT_MODE="persistent"
  fi
  export WORKBOT_REDIS_URL
  export WORKBOT_NATS_URL
  export WORKBOT_CHROMA_URL
  export WORKBOT_CHROMA_PERSIST_PATH
  "${ALEMBIC_BIN}" upgrade head
  exec "${VENV_PYTHON}" -m uvicorn app.main:app --host "${BACKEND_HOST}" --port "${BACKEND_PORT}"
) &
BACKEND_PID=$!

echo "Starting frontend on http://${FRONTEND_HOST}:${FRONTEND_PORT}"
(
  cd "${FRONTEND_DIR}"
  export NEXT_PUBLIC_API_BASE_URL
  export NEXT_PUBLIC_WS_BASE_URL
  exec npm run dev -- --hostname "${FRONTEND_HOST}" --port "${FRONTEND_PORT}"
) &
FRONTEND_PID=$!

echo
echo "WorkBot dev servers are starting..."
echo "Frontend: http://${FRONTEND_HOST}:${FRONTEND_PORT}"
echo "Backend:  http://${BACKEND_HOST}:${BACKEND_PORT}"
echo "API Base: ${NEXT_PUBLIC_API_BASE_URL}"
if [[ "${INFRA_MODE}" == "docker" ]]; then
  echo "Infra:    docker postgres=${POSTGRES_PORT} redis=${REDIS_PORT} nats=${NATS_PORT} chroma=${CHROMA_PORT}"
else
  echo "Infra:    fallback sqlite + in-process degradation for redis/nats/chroma"
fi
echo "Login:    http://${FRONTEND_HOST}:${FRONTEND_PORT}/login"
echo "Demo:     admin@workbot.ai / workbot123"
echo "Press Ctrl+C once to stop both."

server_exit_code=0

while true; do
  if ! kill -0 "${BACKEND_PID}" 2>/dev/null; then
    wait "${BACKEND_PID}" || server_exit_code=$?
    echo
    echo "Backend exited."
    break
  fi

  if ! kill -0 "${FRONTEND_PID}" 2>/dev/null; then
    wait "${FRONTEND_PID}" || server_exit_code=$?
    echo
    echo "Frontend exited."
    break
  fi

  sleep 1
done

exit "${server_exit_code}"
