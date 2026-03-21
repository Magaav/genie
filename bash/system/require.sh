#!/bin/bash

set -e

# Get Bash Variables
source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/env.sh"

ACTUAL_USER="${SUDO_USER:-$USER}"

install_base_packages() {
  require "nano"
  require "net-tools"
  require "cron"

  run_as_root systemctl enable cron
  run_as_root systemctl start cron
}

set_docker() {
  require "ca-certificates"
  require "curl"

  if command -v docker >/dev/null 2>&1; then
    echo "Docker is already installed."
  else
    curl -fsSL https://get.docker.com | sh
  fi

  run_as_root systemctl enable docker
  run_as_root systemctl start docker

  if id -nG "$ACTUAL_USER" | tr ' ' '\n' | grep -qx docker; then
    echo "User $ACTUAL_USER is already in the docker group."
  else
    run_as_root usermod -aG docker "$ACTUAL_USER"
    echo "Added $ACTUAL_USER to the docker group."
    echo "Open a new shell or run: newgrp docker"
  fi
}

case "$1" in
  base)
    install_base_packages
    ;;
  docker)
    install_base_packages
    set_docker
    ;;
  all|"")
    install_base_packages
    set_docker
    ;;
  *)
    echo "Usage: $0 {base|docker|all}"
    exit 1
    ;;
esac
