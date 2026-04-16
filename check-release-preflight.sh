#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTAINER_NAME="${WORKBOT_BRAIN_CONTAINER_NAME:-workbot-backend}"
CONTAINER_REPO_ROOT="${WORKBOT_BRAIN_REPO_ROOT_IN_CONTAINER:-/workspace}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker command not found. Install Docker Desktop or Docker Engine first."
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon is not running."
  echo "Start Docker Desktop or your Docker service first, then rerun ./check-release-preflight.sh"
  exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "Backend container '$CONTAINER_NAME' is not running."
  echo "Start the brain first with ./run-brain.sh, then rerun ./check-release-preflight.sh"
  exit 1
fi

quoted_args=""
for arg in "$@"; do
  quoted_args+=" $(printf '%q' "$arg")"
done

exec docker exec "$CONTAINER_NAME" sh -lc \
  "cd /app && WORKBOT_REPO_ROOT=$CONTAINER_REPO_ROOT python scripts/check_release_preflight.py --repo-root $CONTAINER_REPO_ROOT --include-live-database$quoted_args"
