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

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  case "$1" in
    permissions) permissions ;;
    *)
      echo "Usage: $0 {permissions}"
      exit 1
    ;;
  esac
fi
