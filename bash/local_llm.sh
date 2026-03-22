#!/bin/bash

set -euo pipefail

source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/env.sh"

LOCAL_LLM_DIR="${LOCAL_LLM_DIR:-/var/lib/openclaw-local-llm}"
LOCAL_LLM_ENV_FILE="${LOCAL_LLM_ENV_FILE:-${LOCAL_LLM_DIR}/local-llm.env}"
OLLAMA_API_URL="${OLLAMA_API_URL:-http://127.0.0.1:11434}"
DEFAULT_MODEL="${DEFAULT_MODEL:-qwen3:8b}"
DEFAULT_EMBED_MODEL="${DEFAULT_EMBED_MODEL:-nomic-embed-text}"
DEFAULT_ROUTE_TIMEOUT_SECONDS="${DEFAULT_ROUTE_TIMEOUT_SECONDS:-8}"
DEFAULT_SUMMARIZE_TIMEOUT_SECONDS="${DEFAULT_SUMMARIZE_TIMEOUT_SECONDS:-8}"
DEFAULT_EXTRACT_TIMEOUT_SECONDS="${DEFAULT_EXTRACT_TIMEOUT_SECONDS:-10}"
DEFAULT_RAW_TIMEOUT_SECONDS="${DEFAULT_RAW_TIMEOUT_SECONDS:-12}"
DEFAULT_LOCAL_MAX_INPUT_CHARS="${DEFAULT_LOCAL_MAX_INPUT_CHARS:-4000}"
DEFAULT_ROUTE_MAX_INPUT_CHARS="${DEFAULT_ROUTE_MAX_INPUT_CHARS:-1800}"

if [ -f "$LOCAL_LLM_ENV_FILE" ]; then
  # shellcheck disable=SC1090
  source "$LOCAL_LLM_ENV_FILE"
fi

QWEN_MODEL="${QWEN_MODEL:-$DEFAULT_MODEL}"
EMBED_MODEL="${EMBED_MODEL:-$DEFAULT_EMBED_MODEL}"
ROUTE_TIMEOUT_SECONDS="${ROUTE_TIMEOUT_SECONDS:-$DEFAULT_ROUTE_TIMEOUT_SECONDS}"
SUMMARIZE_TIMEOUT_SECONDS="${SUMMARIZE_TIMEOUT_SECONDS:-$DEFAULT_SUMMARIZE_TIMEOUT_SECONDS}"
EXTRACT_TIMEOUT_SECONDS="${EXTRACT_TIMEOUT_SECONDS:-$DEFAULT_EXTRACT_TIMEOUT_SECONDS}"
RAW_TIMEOUT_SECONDS="${RAW_TIMEOUT_SECONDS:-$DEFAULT_RAW_TIMEOUT_SECONDS}"
LOCAL_MAX_INPUT_CHARS="${LOCAL_MAX_INPUT_CHARS:-$DEFAULT_LOCAL_MAX_INPUT_CHARS}"
ROUTE_MAX_INPUT_CHARS="${ROUTE_MAX_INPUT_CHARS:-$DEFAULT_ROUTE_MAX_INPUT_CHARS}"

usage() {
  cat <<'EOF'
Usage:
  local_llm.sh raw "<prompt>"
  local_llm.sh summarize "<text>"
  local_llm.sh route "<task>"
  local_llm.sh extract "<text>"
  local_llm.sh embed "<text>"
  local_llm.sh policy
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

trim_input() {
  local input_text="$1"
  local limit="$2"

  if [ "${#input_text}" -le "$limit" ]; then
    printf '%s' "$input_text"
  else
    printf '%s' "${input_text:0:limit}"
  fi
}

heuristic_route() {
  local input_text="$1"
  local lower_text

  lower_text="$(printf '%s' "$input_text" | tr '[:upper:]' '[:lower:]')"

  if [ "${#input_text}" -gt "$ROUTE_MAX_INPUT_CHARS" ]; then
    cat <<EOF
LABEL: REMOTE
REASON: Input is too large for fast local routing on this host.
EOF
    return 0
  fi

  if printf '%s' "$lower_text" | rg -q 'architecture|multi-step|plan|design|refactor|code|implement|debug|root cause|incident|agi|memory|retrieval|security|legal|medical|financial'; then
    cat <<EOF
LABEL: REMOTE
REASON: Task appears complex or high-stakes and should skip local deliberation.
EOF
    return 0
  fi

  return 1
}

call_generate() {
  local prompt="$1"
  local timeout_seconds="$2"
  local escaped_prompt

  escaped_prompt="$(json_escape "$prompt")"

  curl -fsS --max-time "$timeout_seconds" "$OLLAMA_API_URL/api/generate" -d "{
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

fallback_output() {
  local mode="$1"

  case "$mode" in
    route)
      cat <<EOF
LABEL: REMOTE
REASON: Local routing timed out or failed on this host.
EOF
      ;;
    summarize)
      echo "LOCAL_SUMMARY_UNAVAILABLE"
      ;;
    extract)
      cat <<EOF
FACTS:
- none
TODO:
- none
CONSTRAINTS:
- none
EOF
      ;;
    raw)
      echo "LOCAL_RAW_UNAVAILABLE"
      ;;
    *)
      echo "LOCAL_UNAVAILABLE"
      ;;
  esac
}

print_policy() {
  cat <<EOF
MODEL: ${QWEN_MODEL}
EMBED_MODEL: ${EMBED_MODEL}
ROUTE_TIMEOUT_SECONDS: ${ROUTE_TIMEOUT_SECONDS}
SUMMARIZE_TIMEOUT_SECONDS: ${SUMMARIZE_TIMEOUT_SECONDS}
EXTRACT_TIMEOUT_SECONDS: ${EXTRACT_TIMEOUT_SECONDS}
RAW_TIMEOUT_SECONDS: ${RAW_TIMEOUT_SECONDS}
LOCAL_MAX_INPUT_CHARS: ${LOCAL_MAX_INPUT_CHARS}
ROUTE_MAX_INPUT_CHARS: ${ROUTE_MAX_INPUT_CHARS}
LOCAL_ALLOWED:
- compression
- extraction
- cleanup
- formatting
- retrieval preparation
REMOTE_REQUIRED:
- deep reasoning
- coding decisions
- multi-step planning
- ambiguous intent
- high-stakes outputs
EOF
}

main() {
  if [ "$#" -lt 1 ]; then
    usage
    exit 1
  fi

  local mode="$1"
  shift
  local input_text="${*:-}"
  local prepared_input
  local prompt
  local timeout_seconds

  require_ollama

  case "$mode" in
    policy)
      print_policy
      ;;
    embed)
      if [ -z "$input_text" ]; then
        usage
        exit 1
      fi
      call_embed "$input_text"
      ;;
    route)
      if [ -z "$input_text" ]; then
        usage
        exit 1
      fi

      if heuristic_route "$input_text"; then
        exit 0
      fi

      prepared_input="$(trim_input "$input_text" "$ROUTE_MAX_INPUT_CHARS")"
      prompt="$(build_prompt "$mode" "$prepared_input")"
      timeout_seconds="$ROUTE_TIMEOUT_SECONDS"
      call_generate "$prompt" "$timeout_seconds" || fallback_output "$mode"
      ;;
    summarize|extract|raw)
      if [ -z "$input_text" ]; then
        usage
        exit 1
      fi

      prepared_input="$(trim_input "$input_text" "$LOCAL_MAX_INPUT_CHARS")"
      prompt="$(build_prompt "$mode" "$prepared_input")"

      case "$mode" in
        summarize) timeout_seconds="$SUMMARIZE_TIMEOUT_SECONDS" ;;
        extract) timeout_seconds="$EXTRACT_TIMEOUT_SECONDS" ;;
        raw) timeout_seconds="$RAW_TIMEOUT_SECONDS" ;;
      esac

      call_generate "$prompt" "$timeout_seconds" || fallback_output "$mode"
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
