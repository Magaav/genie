#!/bin/bash

set -e  # Exit on any error

# Get the directory of this script (env.sh)
ROOT_DIR="$(dirname "$(realpath "${BASH_SOURCE[0]}")")/../.."
INSTANCE_NAME="openclaw.ohana"
INSTANCE_EMAIL="vic.scar@gmail.com"
LOG_DIR="$ROOT_DIR/log"
LOG_BASH_DIR="$LOG_DIR/system/bash"
BASH_DIR="$ROOT_DIR/bash"
NOW=$(date '+%Y-%m-%d_%H-%M-%S')

# Ensure the LOG_BASH_DIR directory exists
mkdir -p "$LOG_BASH_DIR"

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

run_as_root(){
  if [ "${EUID:-$(id -u)}" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
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
export ROOT_DIR
export INSTANCE_NAME
export INSTANCE_EMAIL
export LOG_DIR
export LOG_BASH_DIR

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  case "$1" in
    permissions) permissions ;;
    *)
      echo "Usage: $0 {permissions}"
      exit 1
    ;;
  esac
fi
