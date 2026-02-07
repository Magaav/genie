#!/bin/bash
# Main server management script for Ubuntu 24 Oracle instance
# Run this script as root or with sudo

# Get Bash Variables
source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/env.sh"

# Main script logic to call functions based on the input argument
case "$1" in
  permissions) permissions ;;
  secure) source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/secure.sh" ;;
  setup) source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/setup.sh" ;;
  sync) source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/sync.sh" ;;
  *)
    echo "Usage: $0 {secure}"
    exit 1
  ;;
esac