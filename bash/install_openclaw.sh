#!/bin/bash

set -e

source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/env.sh"

ACTUAL_USER="${SUDO_USER:-$USER}"
ACTUAL_HOME="$(getent passwd "$ACTUAL_USER" | cut -d: -f6)"
OPENCLAW_REPO_DIR="/local/openclaw"
OPENCLAW_CONFIG_DIR="/local/.openclaw"
OPENCLAW_WORKSPACE_DIR="${OPENCLAW_CONFIG_DIR}/workspace"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed. Run: bash /local/bash/system/require.sh docker"
  exit 1
fi

if [ ! -d "$OPENCLAW_REPO_DIR/.git" ]; then
  git clone https://github.com/openclaw/openclaw.git "$OPENCLAW_REPO_DIR"
else
  echo "OpenClaw repository already exists at $OPENCLAW_REPO_DIR"
fi

mkdir -p "$OPENCLAW_CONFIG_DIR" "$OPENCLAW_WORKSPACE_DIR"
chown -R "$ACTUAL_USER:$ACTUAL_USER" "$OPENCLAW_CONFIG_DIR"
chmod 750 "$OPENCLAW_CONFIG_DIR" "$OPENCLAW_WORKSPACE_DIR"

export OPENCLAW_CONFIG_DIR
export OPENCLAW_WORKSPACE_DIR
export OPENCLAW_GATEWAY_BIND=local
export OPENCLAW_GATEWAY_TOKEN="${OPENCLAW_GATEWAY_TOKEN:-$(openssl rand -hex 32)}"

cd "$OPENCLAW_REPO_DIR"
./docker-setup.sh

chown -R "$ACTUAL_USER:$ACTUAL_USER" "$OPENCLAW_CONFIG_DIR"
find "$OPENCLAW_CONFIG_DIR" -type d -exec chmod 750 {} \;
find "$OPENCLAW_CONFIG_DIR" -type f -exec chmod 640 {} \;

if ! grep -Fq "alias openclaw='docker compose -f /local/openclaw/docker-compose.yml exec openclaw-gateway node dist/index.js'" "$ACTUAL_HOME/.bashrc" 2>/dev/null; then
  echo "alias openclaw='docker compose -f /local/openclaw/docker-compose.yml exec openclaw-gateway node dist/index.js'" >> "$ACTUAL_HOME/.bashrc"
fi

echo "OpenClaw install preparation completed."
echo "Repository: $OPENCLAW_REPO_DIR"
echo "Config dir: $OPENCLAW_CONFIG_DIR"
echo "Workspace dir: $OPENCLAW_WORKSPACE_DIR"
echo "Gateway bind: $OPENCLAW_GATEWAY_BIND"
echo "Gateway token: $OPENCLAW_GATEWAY_TOKEN"
echo "Reload your shell to use the 'openclaw' alias."
