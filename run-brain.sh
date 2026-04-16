#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGISTRY_TARGET_DIR="$ROOT_DIR/deploy/external-registry"
REGISTRY_TARGET_FILE="$REGISTRY_TARGET_DIR/workbot_external_sources.local.json"
REGISTRY_SOURCE_FILE="${WORKBOT_EXTERNAL_REGISTRY_SOURCE_FILE:-$ROOT_DIR/../XXL_ExternalConnection/config/workbot_external_sources.combined.json}"
BASE_IMAGE_MIRROR_PREFIX="${WORKBOT_BASE_IMAGE_MIRROR_PREFIX:-docker.1ms.run/library}"
EXTRA_COMPOSE_FILES="${WORKBOT_EXTRA_COMPOSE_FILES:-}"
COMMAND="${1:-up}"

if [[ "$COMMAND" == -* ]]; then
  COMMAND="up"
elif [[ $# -gt 0 ]]; then
  shift
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker command not found. Install Docker Desktop or Docker Engine first."
  exit 1
fi

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
  if docker info >/dev/null 2>&1; then
    return
  fi

  local app_path=""
  app_path="$(docker_app_path)"
  if [[ -n "$app_path" ]] && command -v open >/dev/null 2>&1; then
    echo "Docker daemon is not running. Starting Docker Desktop..."
    open -a Docker >/dev/null 2>&1 || true
  else
    echo "Docker daemon is not running."
    echo "Start Docker Desktop or your Docker service first, then rerun ./run-brain.sh"
    exit 1
  fi

  for _ in $(seq 1 90); do
    if docker info >/dev/null 2>&1; then
      echo "Docker daemon is ready."
      return
    fi
    sleep 2
  done

  echo "Docker daemon did not become ready in time."
  echo "Inspect Docker Desktop, then rerun ./run-brain.sh"
  exit 1
}

ensure_docker

compose_cmd() {
  local args=()
  args+=(-f "$ROOT_DIR/docker-compose.yml")
  if [[ -n "$EXTRA_COMPOSE_FILES" ]]; then
    IFS=':' read -r -a extra_files <<< "$EXTRA_COMPOSE_FILES"
    for file in "${extra_files[@]}"; do
      [[ -n "$file" ]] || continue
      args+=(-f "$ROOT_DIR/$file")
    done
  fi
  docker compose "${args[@]}" "$@"
}

ensure_base_image() {
  local official_image=$1
  local mirror_image="${BASE_IMAGE_MIRROR_PREFIX}/${official_image}"
  local retries="${2:-5}"
  local attempt=1

  if docker image inspect "$official_image" >/dev/null 2>&1; then
    return
  fi

  while (( attempt <= retries )); do
    echo "Prefetching base image via mirror: $mirror_image (attempt $attempt/$retries)"
    if docker pull "$mirror_image"; then
      docker tag "$mirror_image" "$official_image"
      echo "Tagged $mirror_image as $official_image"
      return
    fi
    attempt=$((attempt + 1))
    sleep 2
  done

  echo "Failed to prefetch base image: $official_image"
  echo "Tried mirror image: $mirror_image"
  exit 1
}

if [[ "$COMMAND" == "up" ]]; then
  ensure_base_image "python:3.13-slim"
  ensure_base_image "node:22-alpine"

  if [[ ! -f "$ROOT_DIR/.env" && -f "$ROOT_DIR/.env.example" ]]; then
    cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
    echo "Created $ROOT_DIR/.env from .env.example"
  fi

  mkdir -p "$REGISTRY_TARGET_DIR"
  if [[ -f "$REGISTRY_SOURCE_FILE" ]]; then
    cp "$REGISTRY_SOURCE_FILE" "$REGISTRY_TARGET_FILE"
    echo "Synced external registry snapshot from $REGISTRY_SOURCE_FILE"
  elif [[ ! -f "$REGISTRY_TARGET_FILE" ]]; then
    echo "Missing registry snapshot: $REGISTRY_TARGET_FILE"
    echo "Either place a registry snapshot there, or set WORKBOT_EXTERNAL_REGISTRY_SOURCE_FILE to a valid source file."
    exit 1
  fi
fi

cd "$ROOT_DIR"
export WORKBOT_EXTERNAL_TOOL_SOURCES_FILE="/opt/workbot/external-registry/workbot_external_sources.local.json"
if [[ "$COMMAND" == "up" ]]; then
  exec compose_cmd up -d --build "$@"
fi

exec compose_cmd "$COMMAND" "$@"
