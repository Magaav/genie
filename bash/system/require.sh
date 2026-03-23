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

set_ollama() {
  require "ca-certificates"
  require "curl"

  if command -v ollama >/dev/null 2>&1; then
    echo "Ollama is already installed."
  else
    curl -fsSL https://ollama.com/install.sh | sh
  fi

  run_as_root mkdir -p /etc/systemd/system/ollama.service.d
  cat <<'EOF' | run_as_root tee /etc/systemd/system/ollama.service.d/override.conf >/dev/null
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
EOF

  run_as_root systemctl daemon-reload
  run_as_root systemctl enable ollama
  run_as_root systemctl restart ollama
}

case "$1" in
  base)
    install_base_packages
    ;;
  docker)
    install_base_packages
    set_docker
    ;;
  ollama)
    install_base_packages
    set_ollama
    ;;
  all|"")
    install_base_packages
    set_docker
    ;;
  *)
    echo "Usage: $0 {base|docker|ollama|all}"
    exit 1
    ;;
esac
