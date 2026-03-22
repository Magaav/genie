#!/bin/bash

set -euo pipefail

source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/env.sh"

LOCAL_LLM_DIR="${LOCAL_LLM_DIR:-/var/lib/openclaw-local-llm}"
LOCAL_LLM_ENV_FILE="${LOCAL_LLM_ENV_FILE:-${LOCAL_LLM_DIR}/local-llm.env}"
OLLAMA_API_URL="${OLLAMA_API_URL:-http://127.0.0.1:11434}"
DEFAULT_MODEL="${DEFAULT_MODEL:-qwen3:8b}"
DEFAULT_EMBED_MODEL="${DEFAULT_EMBED_MODEL:-nomic-embed-text}"

if [ -f "$LOCAL_LLM_ENV_FILE" ]; then
  # shellcheck disable=SC1090
  source "$LOCAL_LLM_ENV_FILE"
fi

QWEN_MODEL="${QWEN_MODEL:-$DEFAULT_MODEL}"
EMBED_MODEL="${EMBED_MODEL:-$DEFAULT_EMBED_MODEL}"

usage() {
  cat <<'EOF'
Usage:
  local_llm.sh raw "<prompt>"
  local_llm.sh summarize "<text>"
  local_llm.sh route "<task>"
  local_llm.sh extract "<text>"
  local_llm.sh embed "<text>"
EOF
}

json_escape() {
  local input="$1"
  input=${input//\\/\\\\}
  input=${input//\"/\\\"}
  input=${input//$'\n'/\\n}
  input=${input//$'\r'/\\r}
  input=${input//$'\t'/\\t}
  printf '%s' "$input"
}

require_ollama() {
  if ! command -v curl >/dev/null 2>&1; then
    echo "curl is required"
    exit 1
  fi

  if ! curl -fsS "$OLLAMA_API_URL/api/tags" >/dev/null; then
    echo "Ollama API is not reachable at $OLLAMA_API_URL"
    exit 1
  fi
}

call_generate() {
  local prompt="$1"
  local escaped_prompt

  escaped_prompt="$(json_escape "$prompt")"

  curl -fsS "$OLLAMA_API_URL/api/generate" -d "{
    \"model\": \"${QWEN_MODEL}\",
    \"prompt\": \"${escaped_prompt}\",
    \"stream\": false,
    \"think\": false,
    \"options\": {
      \"temperature\": 0,
      \"top_p\": 0.9,
      \"num_ctx\": 4096
    }
  }" | sed -n 's/.*"response":"\(.*\)","done":true.*/\1/p' \
    | sed 's/\\n/\n/g; s/\\"/"/g; s/\\\\/\\/g'
}

call_embed() {
  local prompt="$1"
  local escaped_prompt

  escaped_prompt="$(json_escape "$prompt")"

  curl -fsS "$OLLAMA_API_URL/api/embeddings" -d "{
    \"model\": \"${EMBED_MODEL}\",
    \"prompt\": \"${escaped_prompt}\"
  }"
}

build_prompt() {
  local mode="$1"
  local input_text="$2"

  case "$mode" in
    raw)
      printf '%s' "$input_text"
      ;;
    summarize)
      cat <<EOF
You are a compression worker.
Return only a concise summary.
Keep the answer under 120 words.
Do not explain your process.

Text:
$input_text
EOF
      ;;
    route)
      cat <<EOF
You are a routing worker for an AGI stack.
Choose exactly one label:
LOCAL
REMOTE

Use LOCAL only for lightweight summarization, extraction, cleanup, formatting, or retrieval preparation.
Use REMOTE for deep reasoning, coding decisions, multi-step planning, ambiguous intent, or high-stakes outputs.

Return exactly this format:
LABEL: <LOCAL or REMOTE>
REASON: <one sentence, under 20 words>

Task:
$input_text
EOF
      ;;
    extract)
      cat <<EOF
Extract only the useful structured information.
Return exactly this format:
FACTS:
- ...
TODO:
- ...
CONSTRAINTS:
- ...

If a section is empty, write:
- none

Text:
$input_text
EOF
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main() {
  if [ "$#" -lt 2 ]; then
    usage
    exit 1
  fi

  local mode="$1"
  shift
  local input_text="$*"

  require_ollama

  case "$mode" in
    embed)
      call_embed "$input_text"
      ;;
    raw|summarize|route|extract)
      call_generate "$(build_prompt "$mode" "$input_text")"
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
