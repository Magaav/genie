#!/bin/bash

set -euo pipefail

source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/env.sh"

ACTUAL_USER="${SUDO_USER:-$USER}"
ACTUAL_HOME="$(getent passwd "$ACTUAL_USER" | cut -d: -f6)"
ACTUAL_UID="$(id -u "$ACTUAL_USER")"
ACTUAL_GID="$(id -g "$ACTUAL_USER")"
OPENCLAW_NODE_UID="${OPENCLAW_NODE_UID:-1000}"
OPENCLAW_NODE_GID="${OPENCLAW_NODE_GID:-1000}"
OPENCLAW_REPO_URL="${OPENCLAW_REPO_URL:-https://github.com/openclaw/openclaw.git}"
OPENCLAW_PINNED_COMMIT="${OPENCLAW_PINNED_COMMIT:-52a0aa06723fbad5e7c2b0fc07fe04eef433d1c7}"
OPENCLAW_RUNTIME_IMAGE="${OPENCLAW_RUNTIME_IMAGE:-ghcr.io/openclaw/openclaw@sha256:97f106719e545adf49b127ef4e58019beaf7e99702a003727d3d45ccbbb748c0}"
OPENCLAW_REPO_DIR="${OPENCLAW_REPO_DIR:-/local/openclaw}"
OPENCLAW_CONFIG_DIR="${OPENCLAW_CONFIG_DIR:-/local/.openclaw}"
OPENCLAW_WORKSPACE_DIR="${OPENCLAW_WORKSPACE_DIR:-${OPENCLAW_CONFIG_DIR}/workspace}"
OPENCLAW_CONTAINER_WORKSPACE_DIR="${OPENCLAW_CONTAINER_WORKSPACE_DIR:-/home/node/.openclaw/workspace}"
OPENCLAW_GATEWAY_PORT="${OPENCLAW_GATEWAY_PORT:-18789}"
OPENCLAW_BRIDGE_PORT="${OPENCLAW_BRIDGE_PORT:-19790}"
OPENCLAW_GATEWAY_BIND="${OPENCLAW_GATEWAY_BIND:-lan}"
OPENCLAW_RUN_ONBOARD="${OPENCLAW_RUN_ONBOARD:-0}"
OPENCLAW_WAIT_URL="${OPENCLAW_WAIT_URL:-http://127.0.0.1:${OPENCLAW_GATEWAY_PORT}/healthz}"
OPENCLAW_ENV_FILE="${OPENCLAW_REPO_DIR}/.env"
FREEWILLER_GATEWAY_ENV_FILE="${FREEWILLER_GATEWAY_ENV_FILE:-$(resolve_state_dir)/freewiller-gateway.env}"
OPENCLAW_SEED_METADATA_DIR="${OPENCLAW_SEED_METADATA_DIR:-$(resolve_state_dir)/openclaw-seed}"
OPENCLAW_SEED_METADATA_FILE="${OPENCLAW_SEED_METADATA_DIR}/seed.json"
OPENCLAW_COMPOSE_OVERRIDE_FILE="${OPENCLAW_COMPOSE_OVERRIDE_FILE:-${OPENCLAW_SEED_METADATA_DIR}/docker-compose.override.yml}"
OPENCLAW_EXTERNAL_AUTH_DIR="${OPENCLAW_EXTERNAL_AUTH_DIR:-${OPENCLAW_CONFIG_DIR}/external-auth}"
OPENCLAW_CODEX_AUTH_DIR="${OPENCLAW_CODEX_AUTH_DIR:-${OPENCLAW_EXTERNAL_AUTH_DIR}/codex}"
OPENCLAW_CODEX_AUTH_PATH="${OPENCLAW_CODEX_AUTH_PATH:-${ACTUAL_HOME}/.codex/auth.json}"
OPENCLAW_CODEX_HOME="${OPENCLAW_CODEX_HOME:-/home/node/.openclaw/external-auth/codex}"
OPENCLAW_DEFAULT_MODEL="${OPENCLAW_DEFAULT_MODEL:-openai-codex/gpt-5.4}"
OPENCLAW_GATEWAY_TOKEN="${OPENCLAW_GATEWAY_TOKEN:-$(openssl rand -hex 32)}"
FREEWILLER_OPENCLAW_HOOKS_SRC_DIR="${FREEWILLER_OPENCLAW_HOOKS_SRC_DIR:-/local/openclaw-hooks}"
FREEWILLER_OPENCLAW_HOOKS_WORKSPACE_DIR="${FREEWILLER_OPENCLAW_HOOKS_WORKSPACE_DIR:-${OPENCLAW_WORKSPACE_DIR}/hooks}"
FREEWILLER_MEMORY_QUEUE_FILE="${FREEWILLER_MEMORY_QUEUE_FILE:-${OPENCLAW_CONTAINER_WORKSPACE_DIR}/freewiller-ingest/openclaw-memory-queue.jsonl}"
FREEWILLER_MEMORY_BRIDGE_MAX_TEXT_CHARS="${FREEWILLER_MEMORY_BRIDGE_MAX_TEXT_CHARS:-3500}"
OPENCLAW_CODEX_AUTH_SYNCED=0

fail() {
  printf '[install_openclaw] ERROR: %s\n' "$1" >&2
  exit 1
}

log_step() {
  printf '[install_openclaw] %s\n' "$1"
}

openclaw_compose() {
  docker compose -f "$OPENCLAW_REPO_DIR/docker-compose.yml" -f "$OPENCLAW_COMPOSE_OVERRIDE_FILE" "$@"
}

ensure_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    fail "Docker is not installed. Run: bash /local/bash/system/require.sh docker"
  fi

  if ! docker compose version >/dev/null 2>&1; then
    fail "Docker Compose v2 is required"
  fi
}

sync_openclaw_repo() {
  if [ ! -d "$OPENCLAW_REPO_DIR/.git" ]; then
    git clone "$OPENCLAW_REPO_URL" "$OPENCLAW_REPO_DIR"
  fi

  git -C "$OPENCLAW_REPO_DIR" fetch --tags origin
  git -C "$OPENCLAW_REPO_DIR" checkout --detach "$OPENCLAW_PINNED_COMMIT"
  chown -R "$ACTUAL_USER:$ACTUAL_USER" "$OPENCLAW_REPO_DIR"
}

prepare_paths() {
  mkdir -p \
    "$OPENCLAW_CONFIG_DIR/identity" \
    "$OPENCLAW_CONFIG_DIR/agents/main/agent" \
    "$OPENCLAW_CONFIG_DIR/agents/main/sessions" \
    "$OPENCLAW_WORKSPACE_DIR" \
    "$FREEWILLER_OPENCLAW_HOOKS_WORKSPACE_DIR" \
    "$OPENCLAW_CODEX_AUTH_DIR" \
    "$OPENCLAW_SEED_METADATA_DIR"
  chown -R "$OPENCLAW_NODE_UID:$OPENCLAW_NODE_GID" "$OPENCLAW_CONFIG_DIR"
  chown -R "$ACTUAL_USER:$ACTUAL_USER" "$OPENCLAW_SEED_METADATA_DIR"
  chmod 750 "$OPENCLAW_CONFIG_DIR" "$OPENCLAW_WORKSPACE_DIR" "$OPENCLAW_SEED_METADATA_DIR"
}

sync_codex_auth() {
  if [ ! -f "$OPENCLAW_CODEX_AUTH_PATH" ]; then
    OPENCLAW_CODEX_AUTH_SYNCED=0
    log_step "No Codex auth found at $OPENCLAW_CODEX_AUTH_PATH; OpenClaw will require manual provider auth"
    return 0
  fi

  install -d -m 750 -o "$OPENCLAW_NODE_UID" -g "$OPENCLAW_NODE_GID" "$OPENCLAW_CODEX_AUTH_DIR"
  install -m 640 -o "$OPENCLAW_NODE_UID" -g "$OPENCLAW_NODE_GID" "$OPENCLAW_CODEX_AUTH_PATH" "$OPENCLAW_CODEX_AUTH_DIR/auth.json"
  OPENCLAW_CODEX_AUTH_SYNCED=1
}

write_compose_override() {
  cat > "$OPENCLAW_COMPOSE_OVERRIDE_FILE" <<EOF
services:
  openclaw-gateway:
    environment:
      CODEX_HOME: $OPENCLAW_CODEX_HOME
      FREEWILLER_MEMORY_QUEUE_FILE: $FREEWILLER_MEMORY_QUEUE_FILE
      FREEWILLER_MEMORY_BRIDGE_MAX_TEXT_CHARS: "$FREEWILLER_MEMORY_BRIDGE_MAX_TEXT_CHARS"
  openclaw-cli:
    environment:
      CODEX_HOME: $OPENCLAW_CODEX_HOME
EOF

  chown "$ACTUAL_USER:$ACTUAL_USER" "$OPENCLAW_COMPOSE_OVERRIDE_FILE"
  chmod 600 "$OPENCLAW_COMPOSE_OVERRIDE_FILE"
}

write_openclaw_env() {
  cat > "$OPENCLAW_ENV_FILE" <<EOF
OPENCLAW_CONFIG_DIR=$OPENCLAW_CONFIG_DIR
OPENCLAW_WORKSPACE_DIR=$OPENCLAW_WORKSPACE_DIR
OPENCLAW_GATEWAY_PORT=$OPENCLAW_GATEWAY_PORT
OPENCLAW_BRIDGE_PORT=$OPENCLAW_BRIDGE_PORT
OPENCLAW_GATEWAY_BIND=$OPENCLAW_GATEWAY_BIND
OPENCLAW_GATEWAY_TOKEN=$OPENCLAW_GATEWAY_TOKEN
OPENCLAW_IMAGE=$OPENCLAW_RUNTIME_IMAGE
OPENCLAW_ALLOW_INSECURE_PRIVATE_WS=
OPENCLAW_SANDBOX=
OPENCLAW_DOCKER_SOCKET=/var/run/docker.sock
OPENCLAW_TZ=UTC
EOF

  chown "$ACTUAL_USER:$ACTUAL_USER" "$OPENCLAW_ENV_FILE"
  chmod 600 "$OPENCLAW_ENV_FILE"
}

pull_runtime_image() {
  docker pull "$OPENCLAW_RUNTIME_IMAGE"
}

sync_freewiller_openclaw_hooks() {
  local source_dir="$FREEWILLER_OPENCLAW_HOOKS_SRC_DIR"
  local target_dir="$FREEWILLER_OPENCLAW_HOOKS_WORKSPACE_DIR"
  local hook_path
  local hook_name

  if [ ! -d "$source_dir" ]; then
    log_step "No Freewiller OpenClaw hooks found at $source_dir; skipping hook sync"
    return 0
  fi

  mkdir -p "$target_dir"
  for hook_path in "$source_dir"/*; do
    [ -e "$hook_path" ] || continue
    hook_name="$(basename "$hook_path")"
    rm -rf "$target_dir/$hook_name"
    cp -R "$hook_path" "$target_dir/$hook_name"
  done
  chown -R "$OPENCLAW_NODE_UID:$OPENCLAW_NODE_GID" "$target_dir"
  find "$target_dir" -type d -exec chmod 750 {} \;
  find "$target_dir" -type f -exec chmod 640 {} \;
}

run_openclaw_node() {
  openclaw_compose run --rm --no-deps --entrypoint node openclaw-gateway dist/index.js "$@"
}

configure_openclaw_gateway() {
  run_openclaw_node config set gateway.mode local >/dev/null
  run_openclaw_node config set gateway.bind "$OPENCLAW_GATEWAY_BIND" >/dev/null
  run_openclaw_node config set gateway.http.endpoints.responses.enabled true >/dev/null
  run_openclaw_node config set gateway.http.endpoints.chatCompletions.enabled true >/dev/null
  run_openclaw_node config set hooks.internal.enabled true --strict-json >/dev/null
  run_openclaw_node config set hooks.internal.entries.freewiller-memory-bridge.enabled true --strict-json >/dev/null

  if [ "$OPENCLAW_CODEX_AUTH_SYNCED" = "1" ]; then
    run_openclaw_node config set agents.defaults.model.primary "$OPENCLAW_DEFAULT_MODEL" >/dev/null
  fi
}

fix_openclaw_permissions() {
  chown -R "$OPENCLAW_NODE_UID:$OPENCLAW_NODE_GID" "$OPENCLAW_CONFIG_DIR"
  find "$OPENCLAW_CONFIG_DIR" -type d -exec chmod 750 {} \;
  find "$OPENCLAW_CONFIG_DIR" -type f -exec chmod 640 {} \; 2>/dev/null || true
}

start_gateway() {
  openclaw_compose up -d openclaw-gateway
}

restart_gateway() {
  openclaw_compose restart openclaw-gateway >/dev/null
}

wait_for_gateway() {
  local attempt
  for attempt in $(seq 1 60); do
    if curl -fsS "$OPENCLAW_WAIT_URL" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  fail "OpenClaw gateway did not become healthy at $OPENCLAW_WAIT_URL"
}

write_seed_metadata() {
  mkdir -p "$OPENCLAW_SEED_METADATA_DIR"

  cat > "$OPENCLAW_SEED_METADATA_FILE" <<EOF
{
  "source_repo": "$OPENCLAW_REPO_URL",
  "pinned_commit": "$OPENCLAW_PINNED_COMMIT",
  "checked_out_commit": "$(git -C "$OPENCLAW_REPO_DIR" rev-parse HEAD)",
  "runtime_image": "$OPENCLAW_RUNTIME_IMAGE",
  "compose_override_file": "$OPENCLAW_COMPOSE_OVERRIDE_FILE",
  "gateway_bind": "$OPENCLAW_GATEWAY_BIND",
  "gateway_port": $OPENCLAW_GATEWAY_PORT,
  "codex_auth_source": "$OPENCLAW_CODEX_AUTH_PATH",
  "codex_auth_synced": $OPENCLAW_CODEX_AUTH_SYNCED,
  "default_model": "$OPENCLAW_DEFAULT_MODEL",
  "workspace_hooks_dir": "$FREEWILLER_OPENCLAW_HOOKS_WORKSPACE_DIR",
  "freewiller_memory_queue_file": "$FREEWILLER_MEMORY_QUEUE_FILE",
  "recorded_at": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
}
EOF

  chown -R "$ACTUAL_USER:$ACTUAL_USER" "$OPENCLAW_SEED_METADATA_DIR"
  chmod 755 "$OPENCLAW_SEED_METADATA_DIR"
  chmod 644 "$OPENCLAW_SEED_METADATA_FILE"
}

wire_freewiller_gateway() {
  mkdir -p "$(dirname "$FREEWILLER_GATEWAY_ENV_FILE")"

  cat > "$FREEWILLER_GATEWAY_ENV_FILE" <<EOF
FREEWILLER_GATEWAY_URL=http://127.0.0.1:${OPENCLAW_GATEWAY_PORT}
FREEWILLER_GATEWAY_TOKEN=$OPENCLAW_GATEWAY_TOKEN
FREEWILLER_AGENT_ID=main
FREEWILLER_MODEL=${FREEWILLER_MODEL:-openclaw:main}
FREEWILLER_GATEWAY_API=${FREEWILLER_GATEWAY_API:-auto}
FREEWILLER_USER=${FREEWILLER_USER:-freewiller-local-agent}
FREEWILLER_MAX_OUTPUT_TOKENS=${FREEWILLER_MAX_OUTPUT_TOKENS:-2048}
EOF

  chown "$ACTUAL_USER:$ACTUAL_USER" "$FREEWILLER_GATEWAY_ENV_FILE"
  chmod 600 "$FREEWILLER_GATEWAY_ENV_FILE"
}

install_aliases() {
  local alias_line="alias openclaw='docker compose -f /local/openclaw/docker-compose.yml -f $(resolve_state_dir)/openclaw-seed/docker-compose.override.yml exec openclaw-gateway node dist/index.js'"
  if ! grep -Fq "$alias_line" "$ACTUAL_HOME/.bashrc" 2>/dev/null; then
    echo "$alias_line" >> "$ACTUAL_HOME/.bashrc"
  fi
}

maybe_run_onboard() {
  if [ "$OPENCLAW_RUN_ONBOARD" != "1" ]; then
    return 0
  fi

  run_openclaw_node onboard --mode local --no-install-daemon
}

main() {
  ensure_docker
  log_step "Syncing pinned OpenClaw source seed"
  sync_openclaw_repo

  log_step "Preparing local OpenClaw directories"
  prepare_paths

  log_step "Syncing Codex auth into OpenClaw seed state when available"
  sync_codex_auth

  log_step "Syncing Freewiller-managed OpenClaw hooks into workspace"
  sync_freewiller_openclaw_hooks

  log_step "Writing OpenClaw compose override"
  write_compose_override

  log_step "Writing OpenClaw environment"
  write_openclaw_env

  log_step "Pulling pinned OpenClaw runtime image"
  pull_runtime_image

  log_step "Fixing OpenClaw data directory permissions"
  fix_openclaw_permissions

  log_step "Configuring OpenClaw gateway defaults"
  configure_openclaw_gateway

  log_step "Starting OpenClaw gateway"
  start_gateway
  wait_for_gateway

  log_step "Recording seed metadata and wiring Freewiller gateway"
  write_seed_metadata
  wire_freewiller_gateway
  install_aliases

  if [ "$OPENCLAW_RUN_ONBOARD" = "1" ]; then
    log_step "Running interactive OpenClaw onboarding"
    maybe_run_onboard
  fi

  echo "OpenClaw seed integration completed."
  echo "Repository: $OPENCLAW_REPO_DIR"
  echo "Pinned commit: $OPENCLAW_PINNED_COMMIT"
  echo "Runtime image: $OPENCLAW_RUNTIME_IMAGE"
  echo "Gateway URL: http://127.0.0.1:${OPENCLAW_GATEWAY_PORT}"
  echo "Gateway token: $OPENCLAW_GATEWAY_TOKEN"
  echo "Compose override: $OPENCLAW_COMPOSE_OVERRIDE_FILE"
  echo "Seed metadata: $OPENCLAW_SEED_METADATA_FILE"
  echo "Freewiller gateway config: $FREEWILLER_GATEWAY_ENV_FILE"
  echo "Set OPENCLAW_RUN_ONBOARD=1 if you want the interactive OpenClaw onboarding flow."
}

main "$@"
