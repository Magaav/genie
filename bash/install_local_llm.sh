#!/bin/bash

set -euo pipefail

source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/env.sh"

ACTUAL_USER="${SUDO_USER:-$USER}"
ACTUAL_HOME="$(getent passwd "$ACTUAL_USER" | cut -d: -f6)"
LOCAL_LLM_DIR="${LOCAL_LLM_DIR:-/var/lib/openclaw-local-llm}"
LOCAL_LLM_ENV_FILE="${LOCAL_LLM_ENV_FILE:-${LOCAL_LLM_DIR}/local-llm.env}"
OPENCLAW_GATEWAY_ENV_FILE="${OPENCLAW_GATEWAY_ENV_FILE:-${LOCAL_LLM_DIR}/openclaw-gateway.env}"
QWEN_MODEL="${QWEN_MODEL:-qwen3:8b}"
EMBED_MODEL="${EMBED_MODEL:-nomic-embed-text}"
ROUTE_TIMEOUT_SECONDS="${ROUTE_TIMEOUT_SECONDS:-8}"
SUMMARIZE_TIMEOUT_SECONDS="${SUMMARIZE_TIMEOUT_SECONDS:-8}"
EXTRACT_TIMEOUT_SECONDS="${EXTRACT_TIMEOUT_SECONDS:-10}"
RAW_TIMEOUT_SECONDS="${RAW_TIMEOUT_SECONDS:-12}"
LOCAL_MAX_INPUT_CHARS="${LOCAL_MAX_INPUT_CHARS:-4000}"
ROUTE_MAX_INPUT_CHARS="${ROUTE_MAX_INPUT_CHARS:-1800}"
OPENCLAW_GATEWAY_URL="${OPENCLAW_GATEWAY_URL:-}"
OPENCLAW_GATEWAY_TOKEN="${OPENCLAW_GATEWAY_TOKEN:-}"
OPENCLAW_AGENT_ID="${OPENCLAW_AGENT_ID:-main}"
OPENCLAW_MODEL="${OPENCLAW_MODEL:-openclaw}"
OPENCLAW_USER="${OPENCLAW_USER:-local-agent}"
OPENCLAW_MAX_OUTPUT_TOKENS="${OPENCLAW_MAX_OUTPUT_TOKENS:-2048}"

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
ROUTE_TIMEOUT_SECONDS=$ROUTE_TIMEOUT_SECONDS
SUMMARIZE_TIMEOUT_SECONDS=$SUMMARIZE_TIMEOUT_SECONDS
EXTRACT_TIMEOUT_SECONDS=$EXTRACT_TIMEOUT_SECONDS
RAW_TIMEOUT_SECONDS=$RAW_TIMEOUT_SECONDS
LOCAL_MAX_INPUT_CHARS=$LOCAL_MAX_INPUT_CHARS
ROUTE_MAX_INPUT_CHARS=$ROUTE_MAX_INPUT_CHARS
EOF

  run_as_root chown -R "$ACTUAL_USER:$ACTUAL_USER" "$LOCAL_LLM_DIR"
  run_as_root chmod 755 "$LOCAL_LLM_DIR"
  run_as_root chmod 644 "$LOCAL_LLM_ENV_FILE"
}

persist_gateway_config() {
  cat <<EOF | run_as_root tee "$OPENCLAW_GATEWAY_ENV_FILE" >/dev/null
OPENCLAW_GATEWAY_URL=$OPENCLAW_GATEWAY_URL
OPENCLAW_GATEWAY_TOKEN=$OPENCLAW_GATEWAY_TOKEN
OPENCLAW_AGENT_ID=$OPENCLAW_AGENT_ID
OPENCLAW_MODEL=$OPENCLAW_MODEL
OPENCLAW_USER=$OPENCLAW_USER
OPENCLAW_MAX_OUTPUT_TOKENS=$OPENCLAW_MAX_OUTPUT_TOKENS
EOF

  run_as_root chown "$ACTUAL_USER:$ACTUAL_USER" "$OPENCLAW_GATEWAY_ENV_FILE"
  run_as_root chmod 600 "$OPENCLAW_GATEWAY_ENV_FILE"
}

pull_models() {
  ollama pull "$QWEN_MODEL"
  ollama pull "$EMBED_MODEL"
}

install_aliases() {
  local bashrc_file="${ACTUAL_HOME}/.bashrc"

  if ! grep -Fq "alias llm-local='/local/bash/local_llm.sh'" "$bashrc_file" 2>/dev/null; then
    echo "alias llm-local='/local/bash/local_llm.sh'" >> "$bashrc_file"
  fi

  if ! grep -Fq "alias llm-chat='/local/bash/local_llm.sh raw'" "$bashrc_file" 2>/dev/null; then
    echo "alias llm-chat='/local/bash/local_llm.sh raw'" >> "$bashrc_file"
  fi

  if ! grep -Fq "alias llm-embed='/local/bash/local_llm.sh embed'" "$bashrc_file" 2>/dev/null; then
    echo "alias llm-embed='/local/bash/local_llm.sh embed'" >> "$bashrc_file"
  fi

  if ! grep -Fq "alias llm-memory='python3 /local/bash/local_memory.py'" "$bashrc_file" 2>/dev/null; then
    echo "alias llm-memory='python3 /local/bash/local_memory.py'" >> "$bashrc_file"
  fi

  if ! grep -Fq "alias llm-agent='python3 /local/bash/local_agent.py'" "$bashrc_file" 2>/dev/null; then
    echo "alias llm-agent='python3 /local/bash/local_agent.py'" >> "$bashrc_file"
  fi

  if ! grep -Fq "alias llm-dispatch='python3 /local/bash/local_agent.py dispatch'" "$bashrc_file" 2>/dev/null; then
    echo "alias llm-dispatch='python3 /local/bash/local_agent.py dispatch'" >> "$bashrc_file"
  fi
}

main() {
  ensure_ollama
  persist_config
  persist_gateway_config
  pull_models
  install_aliases

  log "Installed local LLM runtime with ${QWEN_MODEL} and ${EMBED_MODEL}"

  echo "Local LLM installation completed."
  echo "Runtime: ollama"
  echo "Worker model: ${QWEN_MODEL}"
  echo "Embedding model: ${EMBED_MODEL}"
  echo "Config file: ${LOCAL_LLM_ENV_FILE}"
  echo "Gateway config file: ${OPENCLAW_GATEWAY_ENV_FILE}"
  echo "Route timeout: ${ROUTE_TIMEOUT_SECONDS}s"
  echo "Summarize timeout: ${SUMMARIZE_TIMEOUT_SECONDS}s"
  echo "Extract timeout: ${EXTRACT_TIMEOUT_SECONDS}s"
  echo "Raw timeout: ${RAW_TIMEOUT_SECONDS}s"
  echo "Reload your shell to use the llm-local, llm-chat, llm-embed, llm-memory, llm-agent, and llm-dispatch aliases."
}

main "$@"
