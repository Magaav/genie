#!/bin/bash

set -euo pipefail

source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/env.sh"

ACTUAL_USER="${SUDO_USER:-$USER}"
ACTUAL_HOME="$(getent passwd "$ACTUAL_USER" | cut -d: -f6)"
DEFAULT_LOCAL_LLM_DIR="/local/state/genie"
LEGACY_LOCAL_LLM_DIR_PRIMARY="/local/state/freewiller"
LEGACY_LOCAL_LLM_DIR_SECONDARY="/var/lib/freewiller"
LEGACY_LOCAL_LLM_DIR_TERTIARY="/var/lib/openclaw-local-llm"
LOCAL_LLM_DIR="${LOCAL_LLM_DIR:-$DEFAULT_LOCAL_LLM_DIR}"
LOCAL_LLM_ENV_FILE="${LOCAL_LLM_ENV_FILE:-${LOCAL_LLM_DIR}/local-llm.env}"
GENIE_GATEWAY_ENV_FILE="${GENIE_GATEWAY_ENV_FILE:-${LOCAL_LLM_DIR}/genie-gateway.env}"
FREEWILLER_GATEWAY_ENV_FILE="${FREEWILLER_GATEWAY_ENV_FILE:-$GENIE_GATEWAY_ENV_FILE}"
PROVIDER_ROUTING_ENV_FILE="${PROVIDER_ROUTING_ENV_FILE:-${LOCAL_LLM_DIR}/provider-routing.env}"
PROVIDER_REGISTRY_FILE="${PROVIDER_REGISTRY_FILE:-${LOCAL_LLM_DIR}/provider-registry.json}"
LEGACY_GATEWAY_ENV_FILE="${LOCAL_LLM_DIR}/freewiller-gateway.env"
OPENCLAW_GATEWAY_ENV_FILE="${LOCAL_LLM_DIR}/openclaw-gateway.env"
REPO_ENV_FILE="${REPO_ENV_FILE:-$REPO_ENV_FILE_DEFAULT}"
LEGACY_REPO_ENV_FILE_PATH="${LEGACY_REPO_ENV_FILE_PATH:-$LEGACY_REPO_ENV_FILE}"
QWEN_MODEL="${QWEN_MODEL:-qwen3:0.6b}"
EMBED_MODEL="${EMBED_MODEL:-nomic-embed-text}"
ROUTE_TIMEOUT_SECONDS="${ROUTE_TIMEOUT_SECONDS:-8}"
SUMMARIZE_TIMEOUT_SECONDS="${SUMMARIZE_TIMEOUT_SECONDS:-8}"
EXTRACT_TIMEOUT_SECONDS="${EXTRACT_TIMEOUT_SECONDS:-10}"
RAW_TIMEOUT_SECONDS="${RAW_TIMEOUT_SECONDS:-12}"
LOCAL_MAX_INPUT_CHARS="${LOCAL_MAX_INPUT_CHARS:-4000}"
ROUTE_MAX_INPUT_CHARS="${ROUTE_MAX_INPUT_CHARS:-1800}"

strip_wrapping_quotes() {
  local value="${1:-}"
  if [ "${#value}" -ge 2 ]; then
    local first_char="${value:0:1}"
    local last_char="${value: -1}"
    if { [ "$first_char" = "'" ] && [ "$last_char" = "'" ]; } || { [ "$first_char" = '"' ] && [ "$last_char" = '"' ]; }; then
      printf '%s\n' "${value:1:${#value}-2}"
      return 0
    fi
  fi
  printf '%s\n' "$value"
}

ensure_repo_env_file() {
  run_as_root mkdir -p "$(dirname "$REPO_ENV_FILE")"
  if [ ! -f "$REPO_ENV_FILE" ] && [ -f "$LEGACY_REPO_ENV_FILE_PATH" ]; then
    run_as_root mv "$LEGACY_REPO_ENV_FILE_PATH" "$REPO_ENV_FILE"
  fi
  if [ ! -f "$REPO_ENV_FILE" ]; then
    run_as_root touch "$REPO_ENV_FILE"
    run_as_root chmod 600 "$REPO_ENV_FILE"
  fi
}

read_env_value() {
  local env_file="$1"
  local key="$2"
  local raw_value

  if [ ! -f "$env_file" ]; then
    return 1
  fi

  raw_value="$(grep -E "^${key}=" "$env_file" | tail -n 1 | cut -d= -f2- || true)"
  if [ -z "$raw_value" ]; then
    return 1
  fi

  strip_wrapping_quotes "$raw_value"
}

read_persisted_value() {
  local env_file="$1"
  local key="$2"
  local raw_value

  if [ ! -f "$env_file" ]; then
    return 1
  fi

  raw_value="$(grep -E "^${key}=" "$env_file" | tail -n 1 | cut -d= -f2- || true)"
  if [ -z "$raw_value" ]; then
    return 1
  fi

  strip_wrapping_quotes "$raw_value"
}

ensure_repo_env_file

REPO_NVIDIA_API_KEY="$(read_env_value "$REPO_ENV_FILE" NVIDIA_API_KEY || read_env_value "$REPO_ENV_FILE" FREEWILLER_NVIDIA_API_KEY || read_env_value "$REPO_ENV_FILE" NGC_API_KEY || read_env_value "$REPO_ENV_FILE" NVIDIA_KIMI_K25_API_KEY || true)"
REPO_NVIDIA_API_BASE_URL="$(read_env_value "$REPO_ENV_FILE" FREEWILLER_NVIDIA_API_BASE_URL || read_env_value "$REPO_ENV_FILE" NVIDIA_API_BASE_URL || echo https://integrate.api.nvidia.com/v1)"
REPO_NVIDIA_MODEL="$(read_env_value "$REPO_ENV_FILE" FREEWILLER_NVIDIA_MODEL || read_env_value "$REPO_ENV_FILE" NVIDIA_MODEL || echo moonshotai/kimi-k2.5)"
REPO_NVIDIA_API_MODE="$(read_env_value "$REPO_ENV_FILE" FREEWILLER_NVIDIA_API_MODE || read_env_value "$REPO_ENV_FILE" NVIDIA_API_MODE || echo chat)"
REPO_NVIDIA_EXTRA_BODY_JSON="$(read_env_value "$REPO_ENV_FILE" FREEWILLER_NVIDIA_EXTRA_BODY_JSON || read_env_value "$REPO_ENV_FILE" NVIDIA_EXTRA_BODY_JSON || true)"
REPO_NVIDIA_MAX_OUTPUT_TOKENS="$(read_env_value "$REPO_ENV_FILE" FREEWILLER_NVIDIA_MAX_OUTPUT_TOKENS || read_env_value "$REPO_ENV_FILE" NVIDIA_MAX_OUTPUT_TOKENS || echo 1024)"
REPO_OPENROUTER_API_KEY="$(read_env_value "$REPO_ENV_FILE" FREEWILLER_OPENROUTER_API_KEY || read_env_value "$REPO_ENV_FILE" OPENROUTER_API_KEY || true)"
REPO_OPENROUTER_API_BASE_URL="$(read_env_value "$REPO_ENV_FILE" FREEWILLER_OPENROUTER_API_BASE_URL || read_env_value "$REPO_ENV_FILE" OPENROUTER_API_BASE_URL || echo https://openrouter.ai/api/v1)"
REPO_OPENROUTER_MODEL="$(read_env_value "$REPO_ENV_FILE" FREEWILLER_OPENROUTER_MODEL || read_env_value "$REPO_ENV_FILE" OPENROUTER_MODEL || echo openrouter/auto)"
REPO_OPENROUTER_API_MODE="$(read_env_value "$REPO_ENV_FILE" FREEWILLER_OPENROUTER_API_MODE || read_env_value "$REPO_ENV_FILE" OPENROUTER_API_MODE || echo chat)"
REPO_OPENROUTER_MAX_OUTPUT_TOKENS="$(read_env_value "$REPO_ENV_FILE" FREEWILLER_OPENROUTER_MAX_OUTPUT_TOKENS || read_env_value "$REPO_ENV_FILE" OPENROUTER_MAX_OUTPUT_TOKENS || echo 1024)"

if [ -z "$REPO_NVIDIA_EXTRA_BODY_JSON" ] && [[ "$REPO_NVIDIA_MODEL" == "moonshotai/kimi-k2.5"* ]]; then
  REPO_NVIDIA_EXTRA_BODY_JSON='{"thinking":{"type":"disabled"}}'
fi

NVIDIA_API_KEY="${NVIDIA_API_KEY:-${FREEWILLER_NVIDIA_API_KEY:-${NVIDIA_KIMI_K25_API_KEY:-$REPO_NVIDIA_API_KEY}}}"
OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-${FREEWILLER_OPENROUTER_API_KEY:-$REPO_OPENROUTER_API_KEY}}"

FREEWILLER_GATEWAY_URL="${FREEWILLER_GATEWAY_URL:-${OPENCLAW_GATEWAY_URL:-$(read_persisted_value "$FREEWILLER_GATEWAY_ENV_FILE" FREEWILLER_GATEWAY_URL || true)}}"
FREEWILLER_GATEWAY_TOKEN="${FREEWILLER_GATEWAY_TOKEN:-${OPENCLAW_GATEWAY_TOKEN:-$(read_persisted_value "$FREEWILLER_GATEWAY_ENV_FILE" FREEWILLER_GATEWAY_TOKEN || true)}}"
FREEWILLER_AGENT_ID="${FREEWILLER_AGENT_ID:-${OPENCLAW_AGENT_ID:-$(read_persisted_value "$FREEWILLER_GATEWAY_ENV_FILE" FREEWILLER_AGENT_ID || echo main)}}"
FREEWILLER_MODEL="${FREEWILLER_MODEL:-${OPENCLAW_MODEL:-$(read_persisted_value "$FREEWILLER_GATEWAY_ENV_FILE" FREEWILLER_MODEL || echo genie)}}"
FREEWILLER_GATEWAY_API="${FREEWILLER_GATEWAY_API:-${OPENCLAW_GATEWAY_API:-$(read_persisted_value "$FREEWILLER_GATEWAY_ENV_FILE" FREEWILLER_GATEWAY_API || echo auto)}}"
FREEWILLER_USER="${FREEWILLER_USER:-${OPENCLAW_USER:-$(read_persisted_value "$FREEWILLER_GATEWAY_ENV_FILE" FREEWILLER_USER || echo genie-ethics)}}"
FREEWILLER_MAX_OUTPUT_TOKENS="${FREEWILLER_MAX_OUTPUT_TOKENS:-${OPENCLAW_MAX_OUTPUT_TOKENS:-$(read_persisted_value "$FREEWILLER_GATEWAY_ENV_FILE" FREEWILLER_MAX_OUTPUT_TOKENS || echo 2048)}}"
FREEWILLER_ROUTER_DEFAULT_PRIVACY="${FREEWILLER_ROUTER_DEFAULT_PRIVACY:-$(read_persisted_value "$PROVIDER_ROUTING_ENV_FILE" FREEWILLER_ROUTER_DEFAULT_PRIVACY || echo internal)}"
FREEWILLER_ROUTER_ALLOW_PUBLIC_EXTERNAL="${FREEWILLER_ROUTER_ALLOW_PUBLIC_EXTERNAL:-$(read_persisted_value "$PROVIDER_ROUTING_ENV_FILE" FREEWILLER_ROUTER_ALLOW_PUBLIC_EXTERNAL || echo 1)}"
FREEWILLER_ROUTER_ALLOW_INTERNAL_CHEAP="${FREEWILLER_ROUTER_ALLOW_INTERNAL_CHEAP:-$(read_persisted_value "$PROVIDER_ROUTING_ENV_FILE" FREEWILLER_ROUTER_ALLOW_INTERNAL_CHEAP || echo 1)}"
FREEWILLER_FRONTIER_EXHAUSTED_FALLBACK="${FREEWILLER_FRONTIER_EXHAUSTED_FALLBACK:-$(read_persisted_value "$PROVIDER_ROUTING_ENV_FILE" FREEWILLER_FRONTIER_EXHAUSTED_FALLBACK || echo 1)}"
FREEWILLER_FRONTIER_EXHAUSTED="${FREEWILLER_FRONTIER_EXHAUSTED:-$(read_persisted_value "$PROVIDER_ROUTING_ENV_FILE" FREEWILLER_FRONTIER_EXHAUSTED || echo 0)}"
FREEWILLER_USAGE_LEDGER_FILE="${FREEWILLER_USAGE_LEDGER_FILE:-$(read_persisted_value "$PROVIDER_ROUTING_ENV_FILE" FREEWILLER_USAGE_LEDGER_FILE || echo "${LOCAL_LLM_DIR}/telemetry/provider-usage.jsonl")}"
FREEWILLER_CHEAP_PROVIDER_FAMILY="${FREEWILLER_CHEAP_PROVIDER_FAMILY:-$(read_env_value "$REPO_ENV_FILE" FREEWILLER_CHEAP_PROVIDER_FAMILY || read_persisted_value "$PROVIDER_ROUTING_ENV_FILE" FREEWILLER_CHEAP_PROVIDER_FAMILY || true)}"
FREEWILLER_CHEAP_API_BASE_URL="${FREEWILLER_CHEAP_API_BASE_URL:-$(read_env_value "$REPO_ENV_FILE" FREEWILLER_CHEAP_API_BASE_URL || read_persisted_value "$PROVIDER_ROUTING_ENV_FILE" FREEWILLER_CHEAP_API_BASE_URL || true)}"
FREEWILLER_CHEAP_API_KEY="${FREEWILLER_CHEAP_API_KEY:-$(read_env_value "$REPO_ENV_FILE" FREEWILLER_CHEAP_API_KEY || read_persisted_value "$PROVIDER_ROUTING_ENV_FILE" FREEWILLER_CHEAP_API_KEY || true)}"
FREEWILLER_CHEAP_MODEL="${FREEWILLER_CHEAP_MODEL:-$(read_env_value "$REPO_ENV_FILE" FREEWILLER_CHEAP_MODEL || read_persisted_value "$PROVIDER_ROUTING_ENV_FILE" FREEWILLER_CHEAP_MODEL || true)}"
FREEWILLER_CHEAP_API_MODE="${FREEWILLER_CHEAP_API_MODE:-$(read_env_value "$REPO_ENV_FILE" FREEWILLER_CHEAP_API_MODE || read_persisted_value "$PROVIDER_ROUTING_ENV_FILE" FREEWILLER_CHEAP_API_MODE || echo chat)}"
FREEWILLER_CHEAP_EXTRA_BODY_JSON="${FREEWILLER_CHEAP_EXTRA_BODY_JSON:-$(read_env_value "$REPO_ENV_FILE" FREEWILLER_CHEAP_EXTRA_BODY_JSON || read_persisted_value "$PROVIDER_ROUTING_ENV_FILE" FREEWILLER_CHEAP_EXTRA_BODY_JSON || true)}"
FREEWILLER_CHEAP_MAX_OUTPUT_TOKENS="${FREEWILLER_CHEAP_MAX_OUTPUT_TOKENS:-$(read_env_value "$REPO_ENV_FILE" FREEWILLER_CHEAP_MAX_OUTPUT_TOKENS || read_persisted_value "$PROVIDER_ROUTING_ENV_FILE" FREEWILLER_CHEAP_MAX_OUTPUT_TOKENS || echo 1024)}"
FREEWILLER_CHEAP_INPUT_COST_PER_MILLION="${FREEWILLER_CHEAP_INPUT_COST_PER_MILLION:-$(read_persisted_value "$PROVIDER_ROUTING_ENV_FILE" FREEWILLER_CHEAP_INPUT_COST_PER_MILLION || true)}"
FREEWILLER_CHEAP_OUTPUT_COST_PER_MILLION="${FREEWILLER_CHEAP_OUTPUT_COST_PER_MILLION:-$(read_persisted_value "$PROVIDER_ROUTING_ENV_FILE" FREEWILLER_CHEAP_OUTPUT_COST_PER_MILLION || true)}"
FREEWILLER_PUBLIC_PROVIDER_FAMILY="${FREEWILLER_PUBLIC_PROVIDER_FAMILY:-$(read_env_value "$REPO_ENV_FILE" FREEWILLER_PUBLIC_PROVIDER_FAMILY || read_persisted_value "$PROVIDER_ROUTING_ENV_FILE" FREEWILLER_PUBLIC_PROVIDER_FAMILY || true)}"
FREEWILLER_PUBLIC_API_BASE_URL="${FREEWILLER_PUBLIC_API_BASE_URL:-$(read_env_value "$REPO_ENV_FILE" FREEWILLER_PUBLIC_API_BASE_URL || read_persisted_value "$PROVIDER_ROUTING_ENV_FILE" FREEWILLER_PUBLIC_API_BASE_URL || true)}"
FREEWILLER_PUBLIC_API_KEY="${FREEWILLER_PUBLIC_API_KEY:-$(read_env_value "$REPO_ENV_FILE" FREEWILLER_PUBLIC_API_KEY || read_persisted_value "$PROVIDER_ROUTING_ENV_FILE" FREEWILLER_PUBLIC_API_KEY || true)}"
FREEWILLER_PUBLIC_MODEL="${FREEWILLER_PUBLIC_MODEL:-$(read_env_value "$REPO_ENV_FILE" FREEWILLER_PUBLIC_MODEL || read_persisted_value "$PROVIDER_ROUTING_ENV_FILE" FREEWILLER_PUBLIC_MODEL || true)}"
FREEWILLER_PUBLIC_API_MODE="${FREEWILLER_PUBLIC_API_MODE:-$(read_env_value "$REPO_ENV_FILE" FREEWILLER_PUBLIC_API_MODE || read_persisted_value "$PROVIDER_ROUTING_ENV_FILE" FREEWILLER_PUBLIC_API_MODE || echo chat)}"
FREEWILLER_PUBLIC_EXTRA_BODY_JSON="${FREEWILLER_PUBLIC_EXTRA_BODY_JSON:-$(read_env_value "$REPO_ENV_FILE" FREEWILLER_PUBLIC_EXTRA_BODY_JSON || read_persisted_value "$PROVIDER_ROUTING_ENV_FILE" FREEWILLER_PUBLIC_EXTRA_BODY_JSON || true)}"
FREEWILLER_PUBLIC_MAX_OUTPUT_TOKENS="${FREEWILLER_PUBLIC_MAX_OUTPUT_TOKENS:-$(read_env_value "$REPO_ENV_FILE" FREEWILLER_PUBLIC_MAX_OUTPUT_TOKENS || read_persisted_value "$PROVIDER_ROUTING_ENV_FILE" FREEWILLER_PUBLIC_MAX_OUTPUT_TOKENS || echo 1024)}"
FREEWILLER_PUBLIC_INPUT_COST_PER_MILLION="${FREEWILLER_PUBLIC_INPUT_COST_PER_MILLION:-$(read_persisted_value "$PROVIDER_ROUTING_ENV_FILE" FREEWILLER_PUBLIC_INPUT_COST_PER_MILLION || true)}"
FREEWILLER_PUBLIC_OUTPUT_COST_PER_MILLION="${FREEWILLER_PUBLIC_OUTPUT_COST_PER_MILLION:-$(read_persisted_value "$PROVIDER_ROUTING_ENV_FILE" FREEWILLER_PUBLIC_OUTPUT_COST_PER_MILLION || true)}"

if [ -n "$REPO_NVIDIA_API_KEY" ] && [ -z "$FREEWILLER_CHEAP_API_KEY" ]; then
  if [ -z "$FREEWILLER_CHEAP_PROVIDER_FAMILY" ] || [ "$FREEWILLER_CHEAP_PROVIDER_FAMILY" = "generic" ]; then
    FREEWILLER_CHEAP_PROVIDER_FAMILY="nvidia"
  fi
  FREEWILLER_CHEAP_API_BASE_URL="${FREEWILLER_CHEAP_API_BASE_URL:-$REPO_NVIDIA_API_BASE_URL}"
  FREEWILLER_CHEAP_API_KEY="$NVIDIA_API_KEY"
  FREEWILLER_CHEAP_MODEL="${FREEWILLER_CHEAP_MODEL:-$REPO_NVIDIA_MODEL}"
  FREEWILLER_CHEAP_API_MODE="${FREEWILLER_CHEAP_API_MODE:-$REPO_NVIDIA_API_MODE}"
  FREEWILLER_CHEAP_EXTRA_BODY_JSON="${FREEWILLER_CHEAP_EXTRA_BODY_JSON:-$REPO_NVIDIA_EXTRA_BODY_JSON}"
  FREEWILLER_CHEAP_MAX_OUTPUT_TOKENS="${FREEWILLER_CHEAP_MAX_OUTPUT_TOKENS:-$REPO_NVIDIA_MAX_OUTPUT_TOKENS}"
fi

if [ -n "$OPENROUTER_API_KEY" ] && [ -z "$FREEWILLER_PUBLIC_API_KEY" ]; then
  if [ -z "$FREEWILLER_PUBLIC_PROVIDER_FAMILY" ] || [ "$FREEWILLER_PUBLIC_PROVIDER_FAMILY" = "generic" ]; then
    FREEWILLER_PUBLIC_PROVIDER_FAMILY="openrouter"
  fi
  FREEWILLER_PUBLIC_API_BASE_URL="${FREEWILLER_PUBLIC_API_BASE_URL:-$REPO_OPENROUTER_API_BASE_URL}"
  FREEWILLER_PUBLIC_API_KEY="$OPENROUTER_API_KEY"
  FREEWILLER_PUBLIC_MODEL="${FREEWILLER_PUBLIC_MODEL:-$REPO_OPENROUTER_MODEL}"
  FREEWILLER_PUBLIC_API_MODE="${FREEWILLER_PUBLIC_API_MODE:-$REPO_OPENROUTER_API_MODE}"
  FREEWILLER_PUBLIC_MAX_OUTPUT_TOKENS="${FREEWILLER_PUBLIC_MAX_OUTPUT_TOKENS:-$REPO_OPENROUTER_MAX_OUTPUT_TOKENS}"
fi

FREEWILLER_CHEAP_PROVIDER_FAMILY="${FREEWILLER_CHEAP_PROVIDER_FAMILY:-generic}"
FREEWILLER_PUBLIC_PROVIDER_FAMILY="${FREEWILLER_PUBLIC_PROVIDER_FAMILY:-generic}"

if [ "$FREEWILLER_USAGE_LEDGER_FILE" = "/local/state/freewiller/telemetry/provider-usage.jsonl" ] && [ "$LOCAL_LLM_DIR" = "$DEFAULT_LOCAL_LLM_DIR" ]; then
  FREEWILLER_USAGE_LEDGER_FILE="${LOCAL_LLM_DIR}/telemetry/provider-usage.jsonl"
fi

ensure_ollama() {
  if ! command -v ollama >/dev/null 2>&1; then
    echo "Ollama is not installed. Run: bash /local/bash/system/require.sh ollama"
    exit 1
  fi

  run_as_root systemctl enable ollama
  run_as_root systemctl start ollama
}

migrate_legacy_state_dir() {
  if [ -n "${LOCAL_LLM_DIR:-}" ] && [ "$LOCAL_LLM_DIR" != "$DEFAULT_LOCAL_LLM_DIR" ]; then
    return
  fi

  run_as_root mkdir -p "$(dirname "$DEFAULT_LOCAL_LLM_DIR")"

  if [ -d "$LEGACY_LOCAL_LLM_DIR_PRIMARY" ] && [ ! -e "$DEFAULT_LOCAL_LLM_DIR" ]; then
    run_as_root mv "$LEGACY_LOCAL_LLM_DIR_PRIMARY" "$DEFAULT_LOCAL_LLM_DIR"
    return
  fi

  if [ -d "$LEGACY_LOCAL_LLM_DIR_SECONDARY" ] && [ ! -e "$DEFAULT_LOCAL_LLM_DIR" ]; then
    run_as_root mv "$LEGACY_LOCAL_LLM_DIR_SECONDARY" "$DEFAULT_LOCAL_LLM_DIR"
    return
  fi

  if [ -d "$LEGACY_LOCAL_LLM_DIR_TERTIARY" ] && [ ! -e "$DEFAULT_LOCAL_LLM_DIR" ]; then
    run_as_root mv "$LEGACY_LOCAL_LLM_DIR_TERTIARY" "$DEFAULT_LOCAL_LLM_DIR"
  fi
}

persist_config() {
  run_as_root touch "$REPO_ENV_FILE"
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
  run_as_root chown "$ACTUAL_USER:$ACTUAL_USER" "$REPO_ENV_FILE"
  run_as_root chmod 600 "$REPO_ENV_FILE"
}

persist_gateway_config() {
  cat <<EOF | run_as_root tee "$FREEWILLER_GATEWAY_ENV_FILE" >/dev/null
FREEWILLER_GATEWAY_URL=$FREEWILLER_GATEWAY_URL
FREEWILLER_GATEWAY_TOKEN=$FREEWILLER_GATEWAY_TOKEN
FREEWILLER_AGENT_ID=$FREEWILLER_AGENT_ID
FREEWILLER_MODEL=$FREEWILLER_MODEL
FREEWILLER_GATEWAY_API=$FREEWILLER_GATEWAY_API
FREEWILLER_USER=$FREEWILLER_USER
FREEWILLER_MAX_OUTPUT_TOKENS=$FREEWILLER_MAX_OUTPUT_TOKENS
EOF

  run_as_root chown "$ACTUAL_USER:$ACTUAL_USER" "$FREEWILLER_GATEWAY_ENV_FILE"
  run_as_root chmod 600 "$FREEWILLER_GATEWAY_ENV_FILE"

  if [ "$LEGACY_GATEWAY_ENV_FILE" != "$FREEWILLER_GATEWAY_ENV_FILE" ] && [ -f "$LEGACY_GATEWAY_ENV_FILE" ]; then
    run_as_root rm -f "$LEGACY_GATEWAY_ENV_FILE"
  fi

  if [ "$OPENCLAW_GATEWAY_ENV_FILE" != "$FREEWILLER_GATEWAY_ENV_FILE" ] && [ -f "$OPENCLAW_GATEWAY_ENV_FILE" ]; then
    run_as_root rm -f "$OPENCLAW_GATEWAY_ENV_FILE"
  fi
}

persist_provider_routing_config() {
  cat <<EOF | run_as_root tee "$PROVIDER_ROUTING_ENV_FILE" >/dev/null
FREEWILLER_ROUTER_DEFAULT_PRIVACY=$FREEWILLER_ROUTER_DEFAULT_PRIVACY
FREEWILLER_ROUTER_ALLOW_PUBLIC_EXTERNAL=$FREEWILLER_ROUTER_ALLOW_PUBLIC_EXTERNAL
FREEWILLER_ROUTER_ALLOW_INTERNAL_CHEAP=$FREEWILLER_ROUTER_ALLOW_INTERNAL_CHEAP
FREEWILLER_FRONTIER_EXHAUSTED_FALLBACK=$FREEWILLER_FRONTIER_EXHAUSTED_FALLBACK
FREEWILLER_FRONTIER_EXHAUSTED=$FREEWILLER_FRONTIER_EXHAUSTED
FREEWILLER_USAGE_LEDGER_FILE=$FREEWILLER_USAGE_LEDGER_FILE
FREEWILLER_CHEAP_PROVIDER_FAMILY=$FREEWILLER_CHEAP_PROVIDER_FAMILY
NVIDIA_API_KEY=$NVIDIA_API_KEY
FREEWILLER_CHEAP_API_BASE_URL=$FREEWILLER_CHEAP_API_BASE_URL
FREEWILLER_CHEAP_API_KEY=$FREEWILLER_CHEAP_API_KEY
FREEWILLER_CHEAP_MODEL=$FREEWILLER_CHEAP_MODEL
FREEWILLER_CHEAP_API_MODE=$FREEWILLER_CHEAP_API_MODE
FREEWILLER_CHEAP_EXTRA_BODY_JSON=$FREEWILLER_CHEAP_EXTRA_BODY_JSON
FREEWILLER_CHEAP_MAX_OUTPUT_TOKENS=$FREEWILLER_CHEAP_MAX_OUTPUT_TOKENS
FREEWILLER_CHEAP_INPUT_COST_PER_MILLION=$FREEWILLER_CHEAP_INPUT_COST_PER_MILLION
FREEWILLER_CHEAP_OUTPUT_COST_PER_MILLION=$FREEWILLER_CHEAP_OUTPUT_COST_PER_MILLION
FREEWILLER_PUBLIC_PROVIDER_FAMILY=$FREEWILLER_PUBLIC_PROVIDER_FAMILY
OPENROUTER_API_KEY=$OPENROUTER_API_KEY
FREEWILLER_PUBLIC_API_BASE_URL=$FREEWILLER_PUBLIC_API_BASE_URL
FREEWILLER_PUBLIC_API_KEY=$FREEWILLER_PUBLIC_API_KEY
FREEWILLER_PUBLIC_MODEL=$FREEWILLER_PUBLIC_MODEL
FREEWILLER_PUBLIC_API_MODE=$FREEWILLER_PUBLIC_API_MODE
FREEWILLER_PUBLIC_EXTRA_BODY_JSON=$FREEWILLER_PUBLIC_EXTRA_BODY_JSON
FREEWILLER_PUBLIC_MAX_OUTPUT_TOKENS=$FREEWILLER_PUBLIC_MAX_OUTPUT_TOKENS
FREEWILLER_PUBLIC_INPUT_COST_PER_MILLION=$FREEWILLER_PUBLIC_INPUT_COST_PER_MILLION
FREEWILLER_PUBLIC_OUTPUT_COST_PER_MILLION=$FREEWILLER_PUBLIC_OUTPUT_COST_PER_MILLION
EOF

  run_as_root chown "$ACTUAL_USER:$ACTUAL_USER" "$PROVIDER_ROUTING_ENV_FILE"
  run_as_root chmod 600 "$PROVIDER_ROUTING_ENV_FILE"
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

  if ! grep -Fq "alias llm-ingest='python3 /local/bash/local_memory.py ingest'" "$bashrc_file" 2>/dev/null; then
    echo "alias llm-ingest='python3 /local/bash/local_memory.py ingest'" >> "$bashrc_file"
  fi

  if ! grep -Fq "alias llm-memory-stats='python3 /local/bash/local_memory.py stats'" "$bashrc_file" 2>/dev/null; then
    echo "alias llm-memory-stats='python3 /local/bash/local_memory.py stats'" >> "$bashrc_file"
  fi

  if ! grep -Fq "alias llm-agent='python3 /local/bash/local_agent.py'" "$bashrc_file" 2>/dev/null; then
    echo "alias llm-agent='python3 /local/bash/local_agent.py'" >> "$bashrc_file"
  fi

  if ! grep -Fq "alias llm-router='python3 /local/bash/provider_router.py'" "$bashrc_file" 2>/dev/null; then
    echo "alias llm-router='python3 /local/bash/provider_router.py'" >> "$bashrc_file"
  fi

  if ! grep -Fq "alias llm-dispatch='python3 /local/bash/local_agent.py dispatch'" "$bashrc_file" 2>/dev/null; then
    echo "alias llm-dispatch='python3 /local/bash/local_agent.py dispatch'" >> "$bashrc_file"
  fi

  if ! grep -Fq "alias genie-backup='bash /local/bash/backup_genie.sh'" "$bashrc_file" 2>/dev/null; then
    echo "alias genie-backup='bash /local/bash/backup_genie.sh'" >> "$bashrc_file"
  fi

}

sync_provider_registry() {
  if [ -n "${NVIDIA_API_KEY:-}" ] || [ -n "${OPENROUTER_API_KEY:-}" ]; then
    python3 "$ROOT_DIR/bash/provider_router.py" discover --provider-family all --sync >/tmp/genie-provider-sync.json
  else
    python3 "$ROOT_DIR/bash/provider_router.py" sync >/tmp/genie-provider-sync.json
  fi
  cat /tmp/genie-provider-sync.json
  rm -f /tmp/genie-provider-sync.json
}

main() {
  ensure_ollama
  migrate_legacy_state_dir
  persist_config
  persist_gateway_config
  persist_provider_routing_config
  sync_provider_registry
  pull_models
  install_aliases

  log "Installed local LLM runtime with ${QWEN_MODEL} and ${EMBED_MODEL}"

  echo "Local LLM installation completed."
  echo "Runtime: ollama"
  echo "Worker model: ${QWEN_MODEL}"
  echo "Embedding model: ${EMBED_MODEL}"
  echo "Config file: ${LOCAL_LLM_ENV_FILE}"
  echo "Gateway config file: ${FREEWILLER_GATEWAY_ENV_FILE}"
  echo "Provider routing file: ${PROVIDER_ROUTING_ENV_FILE}"
  echo "Provider registry file: ${PROVIDER_REGISTRY_FILE}"
  echo "Route timeout: ${ROUTE_TIMEOUT_SECONDS}s"
  echo "Summarize timeout: ${SUMMARIZE_TIMEOUT_SECONDS}s"
  echo "Extract timeout: ${EXTRACT_TIMEOUT_SECONDS}s"
  echo "Raw timeout: ${RAW_TIMEOUT_SECONDS}s"
  if [ -n "$FREEWILLER_CHEAP_API_KEY" ] && [ -n "$FREEWILLER_CHEAP_MODEL" ]; then
    echo "Cheap lane: ${FREEWILLER_CHEAP_PROVIDER_FAMILY} -> ${FREEWILLER_CHEAP_MODEL}"
  else
    echo "Cheap lane: not configured"
  fi
  echo "Reload your shell to use the llm-local, llm-chat, llm-embed, llm-memory, llm-ingest, llm-memory-stats, llm-agent, llm-router, llm-dispatch, and genie-backup aliases."
}

main "$@"
