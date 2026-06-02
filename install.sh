#!/usr/bin/env bash
set -euo pipefail

compose_url="${ORION_COMPOSE_URL:-https://raw.githubusercontent.com/krstalacam/orion-router/main/docker-compose.ghcr.yml}"
env_example_url="${ORION_ENV_EXAMPLE_URL:-https://raw.githubusercontent.com/krstalacam/orion-router/main/.env.example}"
project_name="orion-router"
network_name="${ORION_NETWORK:-orion-network}"
work_dir="${HOME}/.orion-router"
compose_file="$work_dir/docker-compose.ghcr.yml"
env_example_file="$work_dir/.env.example"
env_file="$work_dir/.env"

mkdir -p "$work_dir"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker not found. Please install Docker Desktop first." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose is not available. Please update Docker Desktop." >&2
  exit 1
fi

if command -v curl >/dev/null 2>&1; then
  curl -fsSL "$compose_url" -o "$compose_file"
  curl -fsSL "$env_example_url" -o "$env_example_file"
elif command -v wget >/dev/null 2>&1; then
  wget -qO "$compose_file" "$compose_url"
  wget -qO "$env_example_file" "$env_example_url"
else
  echo "curl or wget is required to download the compose file." >&2
  exit 1
fi

if ! grep -q "^services:" "$compose_file"; then
  echo "Downloaded file does not look like a Docker Compose file." >&2
  exit 1
fi

if [ ! -f "$env_file" ]; then
  cp "$env_example_file" "$env_file"
fi

if ! docker network inspect "$network_name" >/dev/null 2>&1; then
  docker network create "$network_name" >/dev/null 2>&1
else
  echo "Network already exists: $network_name"
fi

for name in router router-db; do
  if docker ps -a --format '{{.Names}}' | grep -qx "$name"; then
    label="$(docker inspect -f '{{ if index .Config.Labels "com.docker.compose.project" }}{{ index .Config.Labels "com.docker.compose.project" }}{{end}}' "$name" 2>/dev/null || true)"
    if [ -n "$label" ] && [ "$label" != "$project_name" ]; then
      echo "Removing conflicting container: $name (project $label)"
      docker rm -f "$name" >/dev/null 2>&1 || true
    else
      echo "Container already exists: $name"
    fi
  fi
done

(
  cd "$work_dir"
  docker compose --project-name "$project_name" -f "$compose_file" up -d
)

echo "Orion Router is up. Dashboard: http://localhost:20128/dashboard"
