#!/bin/bash

set -e  # Exit on any error

# Get the directory of this script (env.sh)
ROOT_DIR="$(dirname "$(realpath "${BASH_SOURCE[0]}")")/../.."
DOCKER_DIR="$ROOT_DIR/docker"
COMPOSE_FILE_DEFAULT="$DOCKER_DIR/compose.yml"
ACCESS_ENV_FILE_DEFAULT="$DOCKER_DIR/access.env"
CONF_ENV_FILE_DEFAULT="$DOCKER_DIR/conf.env"
LEGACY_DOCKER_ENV_FILE="$DOCKER_DIR/.env"
LEGACY_ROOT_ENV_FILE="$ROOT_DIR/.env"
INSTANCE_NAME="genie.ohana"
INSTANCE_EMAIL="vic.scar@gmail.com"
GENIE_STATE_DIR_DEFAULT="/local/state/genie"
GENIE_MEMORY_DIR_DEFAULT="${GENIE_STATE_DIR_DEFAULT}/memory"
GENIE_POLICY_DIR_DEFAULT="${GENIE_STATE_DIR_DEFAULT}/policy"
GENIE_GATEWAY_STATE_DIR_DEFAULT="${GENIE_STATE_DIR_DEFAULT}/gateway"
GENIE_TELEMETRY_DIR_DEFAULT="${GENIE_STATE_DIR_DEFAULT}/telemetry"
GENIE_RUNTIME_DIR_DEFAULT="${GENIE_STATE_DIR_DEFAULT}/runtime"
GENIE_PROJECTIONS_DIR_DEFAULT="${GENIE_MEMORY_DIR_DEFAULT}/projections"
GENIE_PACKAGES_DIR_DEFAULT="${GENIE_RUNTIME_DIR_DEFAULT}/packages"
GENIE_RESPONSES_DIR_DEFAULT="${GENIE_RUNTIME_DIR_DEFAULT}/responses"
GENIE_BRIDGE_DIR_DEFAULT="${GENIE_RUNTIME_DIR_DEFAULT}/bridge"
GENIE_FRONTIER_DIR_DEFAULT="${GENIE_RUNTIME_DIR_DEFAULT}/frontier"
GENIE_WORKCELLS_DIR_DEFAULT="${GENIE_RUNTIME_DIR_DEFAULT}/workcells"
GENIE_REVIEW_QUEUE_DEFAULT="${GENIE_RUNTIME_DIR_DEFAULT}/review-queue.jsonl"
GENIE_CONTROL_LOG_DEFAULT="${GENIE_RUNTIME_DIR_DEFAULT}/control-log.jsonl"
GENIE_LOCAL_LLM_ENV_DEFAULT="${GENIE_POLICY_DIR_DEFAULT}/local-llm.env"
GENIE_GATEWAY_ENV_DEFAULT="${GENIE_POLICY_DIR_DEFAULT}/genie-gateway.env"
GENIE_PROVIDER_ROUTING_ENV_DEFAULT="${GENIE_POLICY_DIR_DEFAULT}/provider-routing.env"
GENIE_PROVIDER_REGISTRY_DEFAULT="${GENIE_POLICY_DIR_DEFAULT}/provider-registry.json"
GENIE_CAPABILITY_REGISTRY_DEFAULT="${GENIE_POLICY_DIR_DEFAULT}/capability-registry.json"
LEGACY_STATE_DIR_PRIMARY="/local/state/freewiller"
LEGACY_STATE_DIR_SECONDARY="/var/lib/freewiller"
LEGACY_STATE_DIR_TERTIARY="/var/lib/openclaw-local-llm"
GENIE_LOG_DIR_DEFAULT="/local/log/genie"
LEGACY_LOG_DIR_PRIMARY="/local/log/freewiller"
LEGACY_LOG_DIR_SECONDARY="/var/log/freewiller"
LEGACY_LOG_DIR_TERTIARY="/var/log/openclaw"
LOG_DIR="${GENIE_LOG_DIR:-${FREEWILLER_LOG_DIR:-${OPENCLAW_LOG_DIR:-$GENIE_LOG_DIR_DEFAULT}}}"
LOG_BASH_DIR="$LOG_DIR/system/bash"
BASH_DIR="$ROOT_DIR/bash"
NOW=$(date '+%Y-%m-%d_%H-%M-%S')

run_as_root(){
  if [ "${EUID:-$(id -u)}" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

is_access_env_key() {
  case "$1" in
    *TOKEN*|*API_KEY*|*SECRET*|*PASSWORD*|*PRIVATE_KEY*|*SSH_KEY*|*KEY_B64*)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

split_env_file_to_paths() {
  local source_file="$1"
  local access_file="$2"
  local conf_file="$3"
  local access_tmp
  local conf_tmp
  local raw_line
  local trimmed
  local key

  access_tmp="$(mktemp)"
  conf_tmp="$(mktemp)"

  while IFS= read -r raw_line || [ -n "$raw_line" ]; do
    trimmed="${raw_line#"${raw_line%%[![:space:]]*}"}"
    if [ -z "$trimmed" ] || [[ "$trimmed" == \#* ]] || [[ "$trimmed" != *=* ]]; then
      continue
    fi
    key="${trimmed%%=*}"
    key="${key//[[:space:]]/}"
    if is_access_env_key "$key"; then
      printf '%s\n' "$trimmed" >> "$access_tmp"
    else
      printf '%s\n' "$trimmed" >> "$conf_tmp"
    fi
  done < "$source_file"

  run_as_root mkdir -p "$(dirname "$access_file")"
  run_as_root install -m 600 "$access_tmp" "$access_file"
  run_as_root install -m 600 "$conf_tmp" "$conf_file"
  rm -f "$access_tmp" "$conf_tmp"
}

ensure_split_env_files() {
  local access_file="${1:-$ACCESS_ENV_FILE_DEFAULT}"
  local conf_file="${2:-$CONF_ENV_FILE_DEFAULT}"

  run_as_root mkdir -p "$(dirname "$access_file")"

  if [ ! -f "$access_file" ] && [ ! -f "$conf_file" ]; then
    if [ -f "$LEGACY_DOCKER_ENV_FILE" ]; then
      split_env_file_to_paths "$LEGACY_DOCKER_ENV_FILE" "$access_file" "$conf_file"
      run_as_root rm -f "$LEGACY_DOCKER_ENV_FILE"
    elif [ -f "$LEGACY_ROOT_ENV_FILE" ]; then
      split_env_file_to_paths "$LEGACY_ROOT_ENV_FILE" "$access_file" "$conf_file"
      run_as_root rm -f "$LEGACY_ROOT_ENV_FILE"
    fi
  fi

  if [ ! -f "$access_file" ]; then
    run_as_root touch "$access_file"
    run_as_root chmod 600 "$access_file"
  fi

  if [ ! -f "$conf_file" ]; then
    run_as_root touch "$conf_file"
    run_as_root chmod 600 "$conf_file"
  fi
}

resolve_state_dir() {
  if [ -n "${LOCAL_LLM_DIR:-}" ]; then
    printf '%s' "$LOCAL_LLM_DIR"
  elif [ -d "$GENIE_STATE_DIR_DEFAULT" ]; then
    printf '%s' "$GENIE_STATE_DIR_DEFAULT"
  elif [ -d "$LEGACY_STATE_DIR_PRIMARY" ]; then
    printf '%s' "$LEGACY_STATE_DIR_PRIMARY"
  elif [ -d "$LEGACY_STATE_DIR_SECONDARY" ]; then
    printf '%s' "$LEGACY_STATE_DIR_SECONDARY"
  elif [ -d "$LEGACY_STATE_DIR_TERTIARY" ]; then
    printf '%s' "$LEGACY_STATE_DIR_TERTIARY"
  else
    printf '%s' "$GENIE_STATE_DIR_DEFAULT"
  fi
}

move_state_file() {
  local source_path="$1"
  local target_path="$2"
  local target_dir
  local migrated_target

  if [ ! -e "$source_path" ] || [ "$source_path" = "$target_path" ]; then
    return
  fi

  target_dir="$(dirname "$target_path")"
  run_as_root mkdir -p "$target_dir"

  if [ -e "$target_path" ]; then
    if cmp -s "$source_path" "$target_path" 2>/dev/null; then
      run_as_root rm -f "$source_path"
      return
    fi
    migrated_target="${target_path}.migrated-${NOW}"
    run_as_root mv "$source_path" "$migrated_target"
    return
  fi

  run_as_root mv "$source_path" "$target_path"
}

merge_state_dir() {
  local source_dir="$1"
  local target_dir="$2"
  local entry
  local target_path

  if [ ! -d "$source_dir" ] || [ "$source_dir" = "$target_dir" ]; then
    return
  fi

  run_as_root mkdir -p "$target_dir"

  while IFS= read -r entry; do
    target_path="${target_dir}/$(basename "$entry")"
    if [ -d "$entry" ]; then
      merge_state_dir "$entry" "$target_path"
      run_as_root rmdir "$entry" 2>/dev/null || true
    else
      move_state_file "$entry" "$target_path"
    fi
  done < <(find "$source_dir" -mindepth 1 -maxdepth 1 2>/dev/null | sort)

  run_as_root rmdir "$source_dir" 2>/dev/null || true
}

ensure_state_layout() {
  local state_dir="${1:-$(resolve_state_dir)}"
  local memory_dir="${GENIE_MEMORY_DIR:-${state_dir}/memory}"
  local policy_dir="${GENIE_POLICY_DIR:-${state_dir}/policy}"
  local gateway_dir="${GENIE_GATEWAY_STATE_DIR:-${state_dir}/gateway}"
  local telemetry_dir="${GENIE_TELEMETRY_DIR:-${state_dir}/telemetry}"
  local runtime_dir="${GENIE_RUNTIME_DIR:-${state_dir}/runtime}"
  local projections_dir="${GENIE_PROJECTIONS_DIR:-${memory_dir}/projections}"
  local packages_dir="${GENIE_PACKAGES_DIR:-${runtime_dir}/packages}"
  local responses_dir="${GENIE_RESPONSES_DIR:-${runtime_dir}/responses}"
  local bridge_dir="${GENIE_BRIDGE_DIR:-${runtime_dir}/bridge}"
  local frontier_dir="${GENIE_FRONTIER_DIR:-${runtime_dir}/frontier}"
  local workcells_dir="${GENIE_WORKCELLS_DIR:-${runtime_dir}/workcells}"

  run_as_root mkdir -p \
    "$state_dir" \
    "$memory_dir" \
    "$policy_dir" \
    "$gateway_dir" \
    "$telemetry_dir" \
    "$runtime_dir" \
    "$projections_dir" \
    "$packages_dir" \
    "$responses_dir" \
    "$bridge_dir" \
    "$frontier_dir" \
    "$workcells_dir"

  merge_state_dir "${state_dir}/projections" "$projections_dir"
  merge_state_dir "${state_dir}/packages" "$packages_dir"
  merge_state_dir "${state_dir}/responses" "$responses_dir"
  merge_state_dir "${state_dir}/bridge" "$bridge_dir"
  merge_state_dir "${state_dir}/frontier" "$frontier_dir"
  merge_state_dir "${memory_dir}/responses" "$responses_dir"
  merge_state_dir "${memory_dir}/telemetry" "$telemetry_dir"

  move_state_file "${state_dir}/local-llm.env" "${GENIE_LOCAL_LLM_ENV:-${policy_dir}/local-llm.env}"
  move_state_file "${state_dir}/genie-gateway.env" "${GENIE_GATEWAY_ENV:-${policy_dir}/genie-gateway.env}"
  move_state_file "${state_dir}/freewiller-gateway.env" "${GENIE_GATEWAY_ENV:-${policy_dir}/genie-gateway.env}"
  move_state_file "${state_dir}/openclaw-gateway.env" "${GENIE_GATEWAY_ENV:-${policy_dir}/genie-gateway.env}"
  move_state_file "${state_dir}/provider-routing.env" "${GENIE_PROVIDER_ROUTING_ENV:-${policy_dir}/provider-routing.env}"
  move_state_file "${state_dir}/provider-router.env" "${GENIE_PROVIDER_ROUTING_ENV:-${policy_dir}/provider-routing.env}"
  move_state_file "${state_dir}/provider-registry.json" "${GENIE_PROVIDER_REGISTRY_FILE:-${policy_dir}/provider-registry.json}"
  move_state_file "${state_dir}/capability-registry.json" "${GENIE_CAPABILITY_REGISTRY_FILE:-${policy_dir}/capability-registry.json}"
  move_state_file "${state_dir}/providers.json" "${GENIE_PROVIDER_REGISTRY_FILE:-${policy_dir}/provider-registry.json}"
}

# Ensure the log directory exists outside the repository by default.
run_as_root mkdir -p "$LOG_BASH_DIR"

# Log function
log(){
  local log_string="$1"
  local log_file="${2:-debug.log}"
  local log_path="$LOG_BASH_DIR/$log_file"
  local log_line

  log_line="$(date '+%Y-%m-%d %H:%M:%S') - $log_string"
  touch "$log_path" 2>/dev/null || true

  if [ -w "$log_path" ]; then
    echo "$log_line" >> "$log_path"
  else
    printf '%s\n' "$log_line" | run_as_root tee -a "$log_path" >/dev/null
  fi
}

require(){
  package=$1
  if ! dpkg -l | grep -q "^ii  $package "; then
    echo "Installing $package..."
    sudo apt-get update -y
    sudo apt-get install -y $package
    echo "$package installed successfully."
    log "Installed $package"
  else
    echo "$package is already installed."
  fi
}

permissions() {
  # Set proper permissions for bash scripts
  chmod +x "$BASH_DIR/server.sh"
  chmod +x "$BASH_DIR/system/"*.sh
  sudo chown -R ubuntu:ubuntu "$LOG_DIR"
  log "Permissions set for bash scripts"
}

export -f require
export -f permissions
export -f log
export -f resolve_state_dir
export ROOT_DIR
export DOCKER_DIR
export COMPOSE_FILE_DEFAULT
export ACCESS_ENV_FILE_DEFAULT
export CONF_ENV_FILE_DEFAULT
export LEGACY_DOCKER_ENV_FILE
export LEGACY_ROOT_ENV_FILE
export INSTANCE_NAME
export INSTANCE_EMAIL
export LOG_DIR
export LOG_BASH_DIR
export GENIE_STATE_DIR_DEFAULT
export GENIE_MEMORY_DIR_DEFAULT
export GENIE_POLICY_DIR_DEFAULT
export GENIE_GATEWAY_STATE_DIR_DEFAULT
export GENIE_TELEMETRY_DIR_DEFAULT
export GENIE_RUNTIME_DIR_DEFAULT
export GENIE_PROJECTIONS_DIR_DEFAULT
export GENIE_PACKAGES_DIR_DEFAULT
export GENIE_RESPONSES_DIR_DEFAULT
export GENIE_BRIDGE_DIR_DEFAULT
export GENIE_FRONTIER_DIR_DEFAULT
export GENIE_LOCAL_LLM_ENV_DEFAULT
export GENIE_GATEWAY_ENV_DEFAULT
export GENIE_PROVIDER_ROUTING_ENV_DEFAULT
export GENIE_PROVIDER_REGISTRY_DEFAULT
export LEGACY_STATE_DIR_PRIMARY
export LEGACY_STATE_DIR_SECONDARY
export LEGACY_STATE_DIR_TERTIARY
export GENIE_LOG_DIR_DEFAULT
export LEGACY_LOG_DIR_PRIMARY
export LEGACY_LOG_DIR_SECONDARY
export LEGACY_LOG_DIR_TERTIARY
export -f is_access_env_key
export -f split_env_file_to_paths
export -f ensure_split_env_files
export -f move_state_file
export -f merge_state_dir
export -f ensure_state_layout

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  case "$1" in
    permissions) permissions ;;
    *)
      echo "Usage: $0 {permissions}"
      exit 1
    ;;
  esac
fi
