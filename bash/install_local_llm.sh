#!/bin/bash

set -euo pipefail

source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/env.sh"

ACTUAL_USER="${SUDO_USER:-$USER}"
ACTUAL_HOME="$(getent passwd "$ACTUAL_USER" | cut -d: -f6)"
LOCAL_LLM_DIR="${LOCAL_LLM_DIR:-/var/lib/openclaw-local-llm}"
LOCAL_LLM_ENV_FILE="${LOCAL_LLM_ENV_FILE:-${LOCAL_LLM_DIR}/local-llm.env}"
QWEN_MODEL="${QWEN_MODEL:-qwen3:8b}"
EMBED_MODEL="${EMBED_MODEL:-nomic-embed-text}"

ensure_ollama() {
  if ! command -v ollama >/dev/null 2>&1; then
    echo "Ollama is not installed. Run: bash /local/bash/system/require.sh ollama"
    exit 1
  fi

  run_as_root systemctl enable ollama
  run_as_root systemctl start ollama
}

persist_config() {
  run_as_root mkdir -p "$LOCAL_LLM_DIR"

  cat <<EOF | run_as_root tee "$LOCAL_LLM_ENV_FILE" >/dev/null
QWEN_MODEL=$QWEN_MODEL
EMBED_MODEL=$EMBED_MODEL
EOF

  run_as_root chmod 640 "$LOCAL_LLM_ENV_FILE"
}

pull_models() {
  ollama pull "$QWEN_MODEL"
  ollama pull "$EMBED_MODEL"
}

install_aliases() {
  local bashrc_file="${ACTUAL_HOME}/.bashrc"

  if ! grep -Fq "alias llm-chat='ollama run ${QWEN_MODEL}'" "$bashrc_file" 2>/dev/null; then
    echo "alias llm-chat='ollama run ${QWEN_MODEL}'" >> "$bashrc_file"
  fi

  if ! grep -Fq "alias llm-embed='ollama run ${EMBED_MODEL}'" "$bashrc_file" 2>/dev/null; then
    echo "alias llm-embed='ollama run ${EMBED_MODEL}'" >> "$bashrc_file"
  fi
}

main() {
  ensure_ollama
  persist_config
  pull_models
  install_aliases

  log "Installed local LLM runtime with ${QWEN_MODEL} and ${EMBED_MODEL}"

  echo "Local LLM installation completed."
  echo "Runtime: ollama"
  echo "Worker model: ${QWEN_MODEL}"
  echo "Embedding model: ${EMBED_MODEL}"
  echo "Config file: ${LOCAL_LLM_ENV_FILE}"
  echo "Reload your shell to use the llm-chat and llm-embed aliases."
}

main "$@"
