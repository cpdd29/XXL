#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMAND="${1:-up}"

if [[ "$COMMAND" != "down" ]]; then
  RESOLVED_TOKEN="${WORKBOT_METRICS_SCRAPE_TOKEN:-}"
  if [[ -z "$RESOLVED_TOKEN" && -f "$ROOT_DIR/.env" ]]; then
    RESOLVED_TOKEN="$(grep -E '^WORKBOT_METRICS_SCRAPE_TOKEN=' "$ROOT_DIR/.env" | tail -n 1 | cut -d '=' -f2- || true)"
  fi
  if [[ -z "$RESOLVED_TOKEN" ]]; then
    echo "Missing WORKBOT_METRICS_SCRAPE_TOKEN."
    echo "Set it in the shell or .env before running ./run-monitoring-stack.sh so Prometheus can scrape /api/dashboard/metrics."
    exit 1
  fi
fi

export WORKBOT_EXTRA_COMPOSE_FILES="deploy/monitoring/docker-compose.monitoring.yml${WORKBOT_EXTRA_COMPOSE_FILES:+:$WORKBOT_EXTRA_COMPOSE_FILES}"
exec "$ROOT_DIR/run-brain.sh" "$@"
