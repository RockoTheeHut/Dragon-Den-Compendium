#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required"
  exit 1
fi

SMOKE_PORT="${SMOKE_PORT:-18080}"
export WEB_PORT_BIND="${WEB_PORT_BIND:-127.0.0.1:${SMOKE_PORT}:8000}"
export DJANGO_MIGRATE="${DJANGO_MIGRATE:-1}"
export DJANGO_COLLECTSTATIC="${DJANGO_COLLECTSTATIC:-1}"
export PERF_GUARD_ON_STARTUP="${PERF_GUARD_ON_STARTUP:-0}"

COMPOSE_FILES=(-f docker-compose.yml)
if [[ "${USE_PROD_OVERLAY:-0}" == "1" ]]; then
  COMPOSE_FILES+=(-f docker-compose.prod.yml)
fi

cleanup() {
  docker compose "${COMPOSE_FILES[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "Building web image..."
docker compose "${COMPOSE_FILES[@]}" build web

echo "Starting web container..."
docker compose "${COMPOSE_FILES[@]}" up -d web

CONTAINER_ID="$(docker compose "${COMPOSE_FILES[@]}" ps -q web)"
if [[ -z "${CONTAINER_ID}" ]]; then
  echo "web container did not start"
  exit 1
fi

echo "Waiting for health check..."
for _ in $(seq 1 60); do
  STATUS="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${CONTAINER_ID}")"
  if [[ "${STATUS}" == "healthy" ]]; then
    break
  fi
  if [[ "${STATUS}" == "unhealthy" ]]; then
    echo "Container became unhealthy"
    docker compose "${COMPOSE_FILES[@]}" logs web
    exit 1
  fi
  sleep 2
done

STATUS="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${CONTAINER_ID}")"
if [[ "${STATUS}" != "healthy" ]]; then
  echo "Timed out waiting for healthy status (current: ${STATUS})"
  docker compose "${COMPOSE_FILES[@]}" logs web
  exit 1
fi

echo "Verifying health endpoint..."
curl --fail --silent --show-error "http://127.0.0.1:${SMOKE_PORT}/healthz/" >/dev/null

echo "Docker smoke test passed."
