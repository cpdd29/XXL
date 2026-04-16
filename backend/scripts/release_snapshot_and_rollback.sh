#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
SNAPSHOT_DIR="$BACKEND_DIR/data/release_snapshots"
TIMESTAMP="${TIMESTAMP_OVERRIDE:-$(date +%Y%m%d_%H%M%S)}"

log() {
  echo "[release-snapshot] $*"
}

fail() {
  echo "[release-snapshot] $*" >&2
  exit 1
}

snapshot() {
  local target="$SNAPSHOT_DIR/$TIMESTAMP"
  mkdir -p "$target"
  [[ -f "$ROOT_DIR/.env" ]] && cp "$ROOT_DIR/.env" "$target/root.env"
  [[ -f "$BACKEND_DIR/.env" ]] && cp "$BACKEND_DIR/.env" "$target/backend.env"
  cp "$ROOT_DIR/docker-compose.yml" "$target/docker-compose.yml"
  if command -v docker >/dev/null 2>&1; then
    docker compose -f "$ROOT_DIR/docker-compose.yml" config > "$target/docker-compose.rendered.yml" || true
  fi
  log "snapshot_created=$target"
}

restore() {
  local source="${1:-}"
  [[ -n "$source" ]] || fail "usage: restore <snapshot_dir_name>"
  local target="$SNAPSHOT_DIR/$source"
  [[ -d "$target" ]] || fail "snapshot not found: $target"
  [[ -f "$target/root.env" ]] && cp "$target/root.env" "$ROOT_DIR/.env"
  [[ -f "$target/backend.env" ]] && cp "$target/backend.env" "$BACKEND_DIR/.env"
  [[ -f "$target/docker-compose.yml" ]] && cp "$target/docker-compose.yml" "$ROOT_DIR/docker-compose.yml"
  log "snapshot_restored=$target"
}

case "${1:-snapshot}" in
  snapshot)
    snapshot
    ;;
  restore)
    restore "${2:-}"
    ;;
  *)
    fail "unknown command: ${1:-}"
    ;;
esac
