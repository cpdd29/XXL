#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export WORKBOT_EXTRA_COMPOSE_FILES="deploy/multi-instance/docker-compose.multi-instance.yml${WORKBOT_EXTRA_COMPOSE_FILES:+:$WORKBOT_EXTRA_COMPOSE_FILES}"
exec "$ROOT_DIR/run-brain.sh" "$@"
