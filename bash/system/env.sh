#!/bin/bash

set -e  # Exit on any error

# Get the directory of this script (env.sh)
ROOT_DIR="$(dirname "$(realpath "${BASH_SOURCE[0]}")")/../.."
DOCKER_DIR="$ROOT_DIR/docker"
COMPOSE_FILE_DEFAULT="$DOCKER_DIR/compose.yml"
REPO_ENV_FILE_DEFAULT="$DOCKER_DIR/.env"
LEGACY_REPO_ENV_FILE="$ROOT_DIR/.env"
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
export REPO_ENV_FILE_DEFAULT
export LEGACY_REPO_ENV_FILE
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

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  case "$1" in
    permissions) permissions ;;
    *)
      echo "Usage: $0 {permissions}"
      exit 1
    ;;
  esac
fi
