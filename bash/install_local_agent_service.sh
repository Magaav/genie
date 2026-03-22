#!/bin/bash

set -euo pipefail

source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/env.sh"

ACTUAL_USER="${SUDO_USER:-$USER}"
ACTUAL_HOME="$(getent passwd "$ACTUAL_USER" | cut -d: -f6)"
COMPOSE_FILE="${COMPOSE_FILE:-/local/docker-compose.local-agent.yml}"
LOCAL_LLM_DIR="${LOCAL_LLM_DIR:-/var/lib/openclaw-local-llm}"
LOCAL_LLM_ENV_FILE="${LOCAL_LLM_ENV_FILE:-${LOCAL_LLM_DIR}/local-llm.env}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:18790/health}"

ensure_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is not installed. Run: bash /local/bash/system/require.sh docker"
    exit 1
  fi

  if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose is not available."
    exit 1
  fi
}

ensure_local_llm_config() {
  if [ ! -f "$LOCAL_LLM_ENV_FILE" ]; then
    echo "Local LLM config is missing at $LOCAL_LLM_ENV_FILE"
    echo "Run: bash /local/bash/install_local_llm.sh"
    exit 1
  fi
}

wait_for_health() {
  local attempt
  for attempt in $(seq 1 20); do
    if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  echo "Local agent did not become healthy at $HEALTH_URL"
  exit 1
}

install_aliases() {
  local bashrc_file="${ACTUAL_HOME}/.bashrc"

  if ! grep -Fq "alias local-agent-up='docker compose -f ${COMPOSE_FILE} up -d --build'" "$bashrc_file" 2>/dev/null; then
    echo "alias local-agent-up='docker compose -f ${COMPOSE_FILE} up -d --build'" >> "$bashrc_file"
  fi

  if ! grep -Fq "alias local-agent-logs='docker compose -f ${COMPOSE_FILE} logs -f local-agent'" "$bashrc_file" 2>/dev/null; then
    echo "alias local-agent-logs='docker compose -f ${COMPOSE_FILE} logs -f local-agent'" >> "$bashrc_file"
  fi
}

main() {
  ensure_docker
  ensure_local_llm_config
  run_as_root mkdir -p /var/lib/openclaw-local-llm /var/log/openclaw
  docker compose -f "$COMPOSE_FILE" up -d --build
  wait_for_health
  install_aliases

  log "Started local agent container service"

  echo "Local agent container started."
  echo "Compose file: $COMPOSE_FILE"
  echo "Health URL: http://127.0.0.1:18790/health"
  echo "Reload your shell to use the local-agent-up and local-agent-logs aliases."
}

main "$@"
