#!/bin/bash

set -euo pipefail

source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/env.sh"

ACTUAL_USER="${SUDO_USER:-$USER}"
ACTUAL_HOME="$(getent passwd "$ACTUAL_USER" | cut -d: -f6)"
COMPOSE_FILE="${COMPOSE_FILE:-$COMPOSE_FILE_DEFAULT}"
ACCESS_ENV_FILE="${ACCESS_ENV_FILE:-$ACCESS_ENV_FILE_DEFAULT}"
CONF_ENV_FILE="${CONF_ENV_FILE:-$CONF_ENV_FILE_DEFAULT}"
DEFAULT_LOCAL_LLM_DIR="/local/state/genie"
LEGACY_LOCAL_LLM_DIR_PRIMARY="/local/state/freewiller"
LEGACY_LOCAL_LLM_DIR_SECONDARY="/var/lib/freewiller"
LEGACY_LOCAL_LLM_DIR_TERTIARY="/var/lib/openclaw-local-llm"
DEFAULT_LOG_DIR="/local/log/genie"
LEGACY_LOG_DIR_PRIMARY="/local/log/freewiller"
LEGACY_LOG_DIR_SECONDARY="/var/log/freewiller"
LEGACY_LOG_DIR_TERTIARY="/var/log/openclaw"
LOCAL_LLM_DIR="${LOCAL_LLM_DIR:-$DEFAULT_LOCAL_LLM_DIR}"
POLICY_DIR="${GENIE_POLICY_DIR:-${LOCAL_LLM_DIR}/policy}"
LOCAL_LLM_ENV_FILE="${LOCAL_LLM_ENV_FILE:-${POLICY_DIR}/local-llm.env}"
LEGACY_TELEGRAM_ALLOWLIST_FILE="/local/state/genie/runtime/frontier/openclaw/runtime/credentials/telegram-default-allowFrom.json"
GATEWAY_STATE_DIR="${LOCAL_LLM_DIR}/gateway"
GATEWAY_ALLOWLIST_FILE="${GATEWAY_STATE_DIR}/telegram-allowlist.json"

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

read_compose_env_value() {
  local key="$1"
  local raw_value
  for env_file in "$CONF_ENV_FILE" "$ACCESS_ENV_FILE" "$LEGACY_DOCKER_ENV_FILE" "$LEGACY_ROOT_ENV_FILE"; do
    if [ ! -f "$env_file" ]; then
      continue
    fi
    raw_value="$(grep -E "^${key}=" "$env_file" | tail -n 1 | cut -d= -f2- || true)"
    if [ -n "$raw_value" ]; then
      raw_value="${raw_value#\'}"
      raw_value="${raw_value%\'}"
      raw_value="${raw_value#\"}"
      raw_value="${raw_value%\"}"
      printf '%s\n' "$raw_value"
      return 0
    fi
  done
  return 1
}

resolved_gateway_port() {
  read_compose_env_value GENIE_GATEWAY_PORT || printf '%s\n' "${GENIE_GATEWAY_PORT:-18790}"
}

compose_cmd() {
  docker compose --env-file "$CONF_ENV_FILE" --env-file "$ACCESS_ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

ensure_compose_env_files() {
  ensure_split_env_files "$ACCESS_ENV_FILE" "$CONF_ENV_FILE"
  run_as_root chown "$ACTUAL_USER:$ACTUAL_USER" "$ACCESS_ENV_FILE" "$CONF_ENV_FILE"
  run_as_root chmod 600 "$ACCESS_ENV_FILE" "$CONF_ENV_FILE"
}

merge_legacy_log_dir() {
  local legacy_dir="$1"
  local target_dir="$2"
  local legacy_file
  local relative_path
  local target_file

  if [ ! -d "$legacy_dir" ] || [ "$legacy_dir" = "$target_dir" ]; then
    return
  fi

  run_as_root mkdir -p "$target_dir"

  while IFS= read -r legacy_file; do
    relative_path="${legacy_file#$legacy_dir/}"
    target_file="${target_dir}/${relative_path}"
    run_as_root mkdir -p "$(dirname "$target_file")"

    if [ -f "$target_file" ]; then
      run_as_root bash -lc "cat '$legacy_file' '$target_file' | sort -u > '${target_file}.tmp' && mv '${target_file}.tmp' '$target_file'"
      run_as_root rm -f "$legacy_file"
    else
      run_as_root mv "$legacy_file" "$target_file"
    fi
  done < <(find "$legacy_dir" -type f 2>/dev/null)

  run_as_root find "$legacy_dir" -depth -type d -empty -delete 2>/dev/null || true
  run_as_root rmdir "$legacy_dir" 2>/dev/null || true
}

migrate_legacy_paths() {
  if [ "$LOCAL_LLM_DIR" = "$DEFAULT_LOCAL_LLM_DIR" ] && [ ! -e "$DEFAULT_LOCAL_LLM_DIR" ]; then
    run_as_root mkdir -p "$(dirname "$DEFAULT_LOCAL_LLM_DIR")"

    if [ -d "$LEGACY_LOCAL_LLM_DIR_PRIMARY" ]; then
      run_as_root mv "$LEGACY_LOCAL_LLM_DIR_PRIMARY" "$DEFAULT_LOCAL_LLM_DIR"
    elif [ -d "$LEGACY_LOCAL_LLM_DIR_SECONDARY" ]; then
      run_as_root mv "$LEGACY_LOCAL_LLM_DIR_SECONDARY" "$DEFAULT_LOCAL_LLM_DIR"
    elif [ -d "$LEGACY_LOCAL_LLM_DIR_TERTIARY" ]; then
      run_as_root mv "$LEGACY_LOCAL_LLM_DIR_TERTIARY" "$DEFAULT_LOCAL_LLM_DIR"
    fi
  fi

  if [ "${FREEWILLER_LOG_DIR:-$DEFAULT_LOG_DIR}" = "$DEFAULT_LOG_DIR" ]; then
    run_as_root mkdir -p "$(dirname "$DEFAULT_LOG_DIR")"
    run_as_root mkdir -p "$DEFAULT_LOG_DIR"

    merge_legacy_log_dir "$LEGACY_LOG_DIR_PRIMARY" "$DEFAULT_LOG_DIR"
    merge_legacy_log_dir "$LEGACY_LOG_DIR_SECONDARY" "$DEFAULT_LOG_DIR"
    merge_legacy_log_dir "$LEGACY_LOG_DIR_TERTIARY" "$DEFAULT_LOG_DIR"
  fi
}

migrate_legacy_gateway_state() {
  run_as_root mkdir -p "$GATEWAY_STATE_DIR"
  if [ ! -f "$GATEWAY_ALLOWLIST_FILE" ] && [ -f "$LEGACY_TELEGRAM_ALLOWLIST_FILE" ]; then
    run_as_root cp "$LEGACY_TELEGRAM_ALLOWLIST_FILE" "$GATEWAY_ALLOWLIST_FILE"
    run_as_root chown "$ACTUAL_USER:$ACTUAL_USER" "$GATEWAY_ALLOWLIST_FILE"
    run_as_root chmod 600 "$GATEWAY_ALLOWLIST_FILE"
  fi
}

wait_for_health() {
  local attempt
  local gateway_port
  local health_url
  gateway_port="$(resolved_gateway_port)"
  health_url="${HEALTH_URL:-http://127.0.0.1:${gateway_port}/health}"
  for attempt in $(seq 1 20); do
    if curl -fsS "$health_url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  echo "Genie gateway did not become healthy at $health_url"
  exit 1
}

install_aliases() {
  local bashrc_file="${ACTUAL_HOME}/.bashrc"

  sed -i '/alias genie-up=/d' "$bashrc_file" 2>/dev/null || true
  echo "alias genie-up='docker compose --env-file ${CONF_ENV_FILE} --env-file ${ACCESS_ENV_FILE} -f ${COMPOSE_FILE} up -d --build --remove-orphans'" >> "$bashrc_file"

  sed -i '/alias genie-logs=/d' "$bashrc_file" 2>/dev/null || true
  echo "alias genie-logs='docker compose --env-file ${CONF_ENV_FILE} --env-file ${ACCESS_ENV_FILE} -f ${COMPOSE_FILE} logs -f gateway ethics state brain instinct'" >> "$bashrc_file"
}

main() {
  ensure_docker
  ensure_compose_env_files
  migrate_legacy_paths
  ensure_state_layout "$LOCAL_LLM_DIR"
  migrate_legacy_gateway_state
  ensure_local_llm_config
  run_as_root mkdir -p /local/docs/generated /local/tests/generated
  run_as_root touch /local/tests/generated/__init__.py
  run_as_root mkdir -p "$LOCAL_LLM_DIR" "${FREEWILLER_LOG_DIR:-$DEFAULT_LOG_DIR}"
  compose_cmd up -d --build --remove-orphans
  wait_for_health
  bash /local/bash/cronjob_genie.sh >/dev/null
  bash /local/bash/cronjob_genie_mind.sh >/dev/null
  bash /local/bash/cronjob_genie_workcell.sh >/dev/null
  bash /local/bash/cronjob_provider_router.sh >/dev/null
  install_aliases

  log "Started Genie native node stack"

  echo "Genie stack started."
  echo "Compose file: $COMPOSE_FILE"
  echo "Health URL: http://127.0.0.1:$(resolved_gateway_port)/health"
  echo "Reload your shell to use the genie-up and genie-logs aliases."
}

main "$@"
