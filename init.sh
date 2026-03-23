#!/bin/bash

# Bootstrap a fresh Oracle/Ubuntu instance for the Genie stack.
#
# Prerequisites:
# 1. Run it as root.
# 2. If you want to clone over SSH instead of the default public HTTPS URL,
#    provide a key with one of:
#    - DEPLOY_KEY_B64: base64-encoded private key content
#    - DEPLOY_KEY_CONTENT: raw private key content
#    - DEPLOY_KEY_PATH: existing private key file path on the instance
#
# Example:
#   sudo bash -lc 'mkdir -p /local && curl -fsSL https://raw.githubusercontent.com/Magaav/genie/master/init.sh | bash'
#
# After completion:
# - open a fresh SSH/VS Code shell, or run `newgrp docker`, before using Docker
#   as the ubuntu user, because the current session will not pick up the new
#   docker group membership automatically
#
# What it does:
# - installs bootstrap packages needed to reach GitHub
# - clones or updates the configured repository into /local
# - runs the repo bootstrap scripts for security and base dependencies
# - installs the local LLM runtime and models
# - optionally restores compact memory from a prior Genie backup
# - installs hourly and daily local backup cron jobs
# - starts the containerized Genie native node stack
# - leaves Docker ready, but you should open a new shell after completion so
#   the ubuntu user picks up the docker group membership

set -euo pipefail

REPO_URL="${REPO_URL:-${REPO_SSH_URL:-https://github.com/Magaav/genie.git}}"
REPO_DIR="${REPO_DIR:-/local}"
BOOTSTRAP_USER="${BOOTSTRAP_USER:-${SUDO_USER:-ubuntu}}"
BOOTSTRAP_HOME="$(getent passwd "$BOOTSTRAP_USER" | cut -d: -f6)"
SSH_DIR="${BOOTSTRAP_HOME}/.ssh"
DEPLOY_KEY_PATH="${DEPLOY_KEY_PATH:-${SSH_DIR}/id_ed25519_bootstrap}"
INSTALL_LOCAL_LLM="${INSTALL_LOCAL_LLM:-1}"
INSTALL_LOCAL_AGENT_SERVICE="${INSTALL_LOCAL_AGENT_SERVICE:-1}"
INSTALL_GENIE_BACKUPS="${INSTALL_GENIE_BACKUPS:-$INSTALL_LOCAL_LLM}"
RESTORE_BACKUP_PATH="${RESTORE_BACKUP_PATH:-}"
RESTORE_BACKUP_URL="${RESTORE_BACKUP_URL:-}"

log() {
  printf '[init] %s\n' "$1"
}

fail() {
  printf '[init] ERROR: %s\n' "$1" >&2
  exit 1
}

require_root() {
  if [ "${EUID}" -ne 0 ]; then
    fail "Run as root: sudo bash /local/init.sh"
  fi
}

install_bootstrap_packages() {
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y git openssh-client ca-certificates curl
}

setup_github_access() {
  if [[ "$REPO_URL" =~ ^https:// ]]; then
    log "Using public HTTPS repository access for ${REPO_URL}"
    return 0
  fi

  mkdir -p "$SSH_DIR"
  chmod 700 "$SSH_DIR"
  touch "${SSH_DIR}/known_hosts"
  chmod 600 "${SSH_DIR}/known_hosts"
  ssh-keyscan github.com >> "${SSH_DIR}/known_hosts" 2>/dev/null || true

  if [ -n "${DEPLOY_KEY_B64:-}" ]; then
    log "Installing deploy key from DEPLOY_KEY_B64"
    printf '%s' "$DEPLOY_KEY_B64" | base64 -d > "$DEPLOY_KEY_PATH"
    chmod 600 "$DEPLOY_KEY_PATH"
  elif [ -n "${DEPLOY_KEY_CONTENT:-}" ]; then
    log "Installing deploy key from DEPLOY_KEY_CONTENT"
    printf '%s\n' "$DEPLOY_KEY_CONTENT" > "$DEPLOY_KEY_PATH"
    chmod 600 "$DEPLOY_KEY_PATH"
  elif [ -f "$DEPLOY_KEY_PATH" ]; then
    log "Using existing deploy key at $DEPLOY_KEY_PATH"
  else
    fail "Provide DEPLOY_KEY_B64, DEPLOY_KEY_CONTENT, or an existing DEPLOY_KEY_PATH for SSH repo access"
  fi

  cat > "${SSH_DIR}/config" <<EOF
Host github.com
  HostName github.com
  User git
  IdentityFile ${DEPLOY_KEY_PATH}
  IdentitiesOnly yes
  StrictHostKeyChecking yes
EOF

  chmod 600 "${SSH_DIR}/config"
  chown -R "${BOOTSTRAP_USER}:${BOOTSTRAP_USER}" "$SSH_DIR"
}

sync_repo() {
  if [ -d "${REPO_DIR}/.git" ]; then
    chown -R "${BOOTSTRAP_USER}:${BOOTSTRAP_USER}" "$REPO_DIR"
    log "Updating existing repository at ${REPO_DIR}"
    sudo -u "$BOOTSTRAP_USER" git -C "$REPO_DIR" pull --ff-only origin master
  else
    local temp_parent_dir
    local temp_clone_dir

    temp_parent_dir="$(mktemp -d)"
    temp_clone_dir="${temp_parent_dir}/repo"
    chown "${BOOTSTRAP_USER}:${BOOTSTRAP_USER}" "$temp_parent_dir"
    log "Cloning repository into temporary directory ${temp_clone_dir}"
    sudo -u "$BOOTSTRAP_USER" git clone "$REPO_URL" "$temp_clone_dir"

    if find "$REPO_DIR" -mindepth 1 -maxdepth 1 ! -name 'init.sh' | grep -q .; then
      rm -rf "$temp_parent_dir"
      fail "${REPO_DIR} contains files other than init.sh and is not a git repository"
    fi

    rm -f "${REPO_DIR}/init.sh"

    log "Moving repository into ${REPO_DIR}"
    find "$temp_clone_dir" -mindepth 1 -maxdepth 1 -exec mv {} "$REPO_DIR"/ \;
    chown -R "${BOOTSTRAP_USER}:${BOOTSTRAP_USER}" "$REPO_DIR"
    rmdir "$temp_clone_dir"
    rmdir "$temp_parent_dir"
  fi
}

fetch_restore_backup() {
  if [ -n "$RESTORE_BACKUP_PATH" ] && [ -n "$RESTORE_BACKUP_URL" ]; then
    fail "Set only one of RESTORE_BACKUP_PATH or RESTORE_BACKUP_URL"
  fi

  if [ -n "$RESTORE_BACKUP_PATH" ]; then
    if [ ! -f "$RESTORE_BACKUP_PATH" ]; then
      fail "RESTORE_BACKUP_PATH does not exist: $RESTORE_BACKUP_PATH"
    fi
    printf '%s' "$RESTORE_BACKUP_PATH"
    return 0
  fi

  if [ -n "$RESTORE_BACKUP_URL" ]; then
    local temp_backup

    temp_backup="$(mktemp /tmp/genie-restore-XXXXXX.tar.gz)"
    log "Downloading restore backup from ${RESTORE_BACKUP_URL}"
    curl -fsSL "$RESTORE_BACKUP_URL" -o "$temp_backup"
    printf '%s' "$temp_backup"
  fi
}

restore_genie_state() {
  local restore_source="$1"

  if [ -z "$restore_source" ]; then
    return 0
  fi

  log "Restoring Genie state from backup"
  LOCAL_LLM_DIR="${REPO_DIR}/state/genie" \
    SUDO_USER="$BOOTSTRAP_USER" \
    bash "${REPO_DIR}/bash/backup_genie.sh" restore "$restore_source" --force

  if [ -n "$RESTORE_BACKUP_URL" ] && [ -f "$restore_source" ]; then
    rm -f "$restore_source"
  fi
}

run_repo_bootstrap() {
  local repo_init="${REPO_DIR}/init.sh"
  local restore_source=""

  if [ ! -f "${REPO_DIR}/bash/system/secure.sh" ]; then
    fail "Repository scripts not found under ${REPO_DIR}/bash"
  fi

  chmod +x "$repo_init" \
    "${REPO_DIR}/bash/system/secure.sh" \
    "${REPO_DIR}/bash/system/require.sh" \
    "${REPO_DIR}/bash/install_local_llm.sh" \
    "${REPO_DIR}/bash/install_local_agent_service.sh" \
    "${REPO_DIR}/bash/backup_genie.sh" \
    "${REPO_DIR}/bash/cronjob_genie.sh" \
    "${REPO_DIR}/bash/cronjob_provider_router.sh" \
    "${REPO_DIR}/bash/local_llm.sh" \
    "${REPO_DIR}/bash/local_memory.py" \
    "${REPO_DIR}/bash/provider_router.py" \
    "${REPO_DIR}/bash/local_agent.py"

  log "Running instance hardening"
  bash "${REPO_DIR}/bash/system/secure.sh"

  log "Running dependency installation"
  SUDO_USER="$BOOTSTRAP_USER" bash "${REPO_DIR}/bash/system/require.sh" docker

  if [ "$INSTALL_LOCAL_LLM" = "1" ]; then
    log "Installing local LLM runtime"
    SUDO_USER="$BOOTSTRAP_USER" bash "${REPO_DIR}/bash/system/require.sh" ollama
    SUDO_USER="$BOOTSTRAP_USER" bash "${REPO_DIR}/bash/install_local_llm.sh"

    restore_source="$(fetch_restore_backup)"
    restore_genie_state "$restore_source"
  fi

  if [ "$INSTALL_GENIE_BACKUPS" = "1" ]; then
    log "Installing local backup cron jobs"
    SUDO_USER="$BOOTSTRAP_USER" bash "${REPO_DIR}/bash/cronjob_genie.sh"
  fi

  if [ "$INSTALL_LOCAL_LLM" = "1" ]; then
    log "Installing provider heartbeat and evaluation cron jobs"
    SUDO_USER="$BOOTSTRAP_USER" bash "${REPO_DIR}/bash/cronjob_provider_router.sh"
  fi

  if [ "$INSTALL_LOCAL_AGENT_SERVICE" = "1" ]; then
    log "Starting Genie native node stack"
    SUDO_USER="$BOOTSTRAP_USER" bash "${REPO_DIR}/bash/install_local_agent_service.sh"
  fi
}

main() {
  require_root

  if [ "$INSTALL_LOCAL_AGENT_SERVICE" = "1" ] && [ "$INSTALL_LOCAL_LLM" != "1" ]; then
    fail "INSTALL_LOCAL_AGENT_SERVICE=1 requires INSTALL_LOCAL_LLM=1"
  fi

  if [ "$INSTALL_GENIE_BACKUPS" = "1" ] && [ "$INSTALL_LOCAL_LLM" != "1" ]; then
    fail "INSTALL_GENIE_BACKUPS=1 requires INSTALL_LOCAL_LLM=1"
  fi

  if { [ -n "$RESTORE_BACKUP_PATH" ] || [ -n "$RESTORE_BACKUP_URL" ]; } && [ "$INSTALL_LOCAL_LLM" != "1" ]; then
    fail "Restoring a backup requires INSTALL_LOCAL_LLM=1"
  fi

  install_bootstrap_packages
  setup_github_access
  sync_repo
  run_repo_bootstrap
  log "Bootstrap completed"
  log "Open a new shell before using docker as ${BOOTSTRAP_USER}"
}

main "$@"
