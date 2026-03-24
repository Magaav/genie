#!/bin/bash

set -euo pipefail

source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/env.sh"

STATE_DIR="${LOCAL_LLM_DIR:-$(resolve_state_dir)}"
BACKUP_ROOT="${BACKUP_ROOT:-/local/backups}"
HOURLY_DIR="${BACKUP_ROOT}/hourly"
DAILY_DIR="${BACKUP_ROOT}/daily"
SNAPSHOT_ROOT_NAME="genie-state"
HOURLY_PREFIX="genie-hourly"
DAILY_PREFIX="genie-daily"
KEEP_HOURLY="${KEEP_HOURLY:-3}"
KEEP_DAILY="${KEEP_DAILY:-1}"
POLICY_DIR="${GENIE_POLICY_DIR:-$STATE_DIR/policy}"
MEMORY_DIR="${GENIE_MEMORY_DIR:-$STATE_DIR/memory}"
TELEMETRY_DIR="${GENIE_TELEMETRY_DIR:-$STATE_DIR/telemetry}"
RUNTIME_DIR="${GENIE_RUNTIME_DIR:-$STATE_DIR/runtime}"
LOCAL_LLM_ENV_FILE="${LOCAL_LLM_ENV_FILE:-$POLICY_DIR/local-llm.env}"
GENIE_GATEWAY_ENV_FILE="${GENIE_GATEWAY_ENV_FILE:-$POLICY_DIR/genie-gateway.env}"
PROVIDER_ROUTING_ENV_FILE="${PROVIDER_ROUTING_ENV_FILE:-$POLICY_DIR/provider-routing.env}"
PROVIDER_REGISTRY_FILE="${PROVIDER_REGISTRY_FILE:-$POLICY_DIR/provider-registry.json}"
CAPABILITY_REGISTRY_FILE="${GENIE_CAPABILITY_REGISTRY_FILE:-$POLICY_DIR/capability-registry.json}"
USAGE_LEDGER_FILE="${FREEWILLER_USAGE_LEDGER_FILE:-$TELEMETRY_DIR/provider-usage.jsonl}"
PROVIDER_HEALTH_FILE="${PROVIDER_HEALTH_FILE:-$TELEMETRY_DIR/provider-health.json}"
PROVIDER_BENCHMARKS_FILE="${PROVIDER_BENCHMARKS_FILE:-$TELEMETRY_DIR/provider-benchmarks.json}"
LOCAL_MEMORY_PY="$(realpath "$ROOT_DIR/bash/local_memory.py")"
ACCESS_ENV_FILE="${ACCESS_ENV_FILE:-$ACCESS_ENV_FILE_DEFAULT}"
CONF_ENV_FILE="${CONF_ENV_FILE:-$CONF_ENV_FILE_DEFAULT}"
LEGACY_DOCKER_ENV_FILE_PATH="${LEGACY_DOCKER_ENV_FILE_PATH:-$LEGACY_DOCKER_ENV_FILE}"
LEGACY_ROOT_ENV_FILE_PATH="${LEGACY_ROOT_ENV_FILE_PATH:-$LEGACY_ROOT_ENV_FILE}"
GATEWAY_STATE_DIR="${GATEWAY_STATE_DIR:-$STATE_DIR/gateway}"
PROJECTIONS_DIR="${PROJECTIONS_DIR:-$MEMORY_DIR/projections}"
REVIEW_QUEUE_FILE="${GENIE_REVIEW_QUEUE_FILE:-$RUNTIME_DIR/review-queue.jsonl}"
CONTROL_LOG_FILE="${GENIE_CONTROL_LOG_FILE:-$RUNTIME_DIR/control-log.jsonl}"
WORKCELLS_DIR="${GENIE_WORKCELLS_DIR:-$RUNTIME_DIR/workcells}"

if [ "${EUID:-$(id -u)}" -eq 0 ]; then
  OWNER_USER="${FREEWILLER_OWNER:-${SUDO_USER:-ubuntu}}"
else
  OWNER_USER="${FREEWILLER_OWNER:-$USER}"
fi
OWNER_GROUP="$(id -gn "$OWNER_USER" 2>/dev/null || echo "$OWNER_USER")"

usage() {
  cat <<'EOF'
Usage:
  backup_genie.sh save {hourly|daily}
  backup_genie.sh restore <backup-file> [--force]
  backup_genie.sh list [hourly|daily|all]
EOF
}

ensure_backup_dirs() {
  run_as_root mkdir -p "$HOURLY_DIR" "$DAILY_DIR"
  run_as_root chown -R "$OWNER_USER:$OWNER_GROUP" "$BACKUP_ROOT"
}

require_state() {
  if [ ! -d "$STATE_DIR" ]; then
    echo "Genie state directory not found at $STATE_DIR"
    exit 1
  fi
}

build_snapshot_dir() {
  local snapshot_dir="$1"
  local compact_memory_path="$snapshot_dir/$SNAPSHOT_ROOT_NAME/memory/entries.compact.jsonl"
  local journal_path="$snapshot_dir/$SNAPSHOT_ROOT_NAME/memory/journal.jsonl"

  mkdir -p "$snapshot_dir/$SNAPSHOT_ROOT_NAME/memory" "$snapshot_dir/$SNAPSHOT_ROOT_NAME/policy"

  if [ -f "$LOCAL_LLM_ENV_FILE" ]; then
    cp "$LOCAL_LLM_ENV_FILE" "$snapshot_dir/$SNAPSHOT_ROOT_NAME/policy/local-llm.env"
  fi

  if [ -f "$GENIE_GATEWAY_ENV_FILE" ]; then
    cp "$GENIE_GATEWAY_ENV_FILE" "$snapshot_dir/$SNAPSHOT_ROOT_NAME/policy/genie-gateway.env"
  elif [ -f "$STATE_DIR/freewiller-gateway.env" ]; then
    cp "$STATE_DIR/freewiller-gateway.env" "$snapshot_dir/$SNAPSHOT_ROOT_NAME/policy/genie-gateway.env"
  fi

  if [ -f "$PROVIDER_ROUTING_ENV_FILE" ]; then
    cp "$PROVIDER_ROUTING_ENV_FILE" "$snapshot_dir/$SNAPSHOT_ROOT_NAME/policy/provider-routing.env"
  fi

  if [ -f "$PROVIDER_REGISTRY_FILE" ]; then
    cp "$PROVIDER_REGISTRY_FILE" "$snapshot_dir/$SNAPSHOT_ROOT_NAME/policy/provider-registry.json"
  fi

  if [ -f "$CAPABILITY_REGISTRY_FILE" ]; then
    cp "$CAPABILITY_REGISTRY_FILE" "$snapshot_dir/$SNAPSHOT_ROOT_NAME/policy/capability-registry.json"
  fi

  if [ -f "$ACCESS_ENV_FILE" ]; then
    cp "$ACCESS_ENV_FILE" "$snapshot_dir/$SNAPSHOT_ROOT_NAME/access.env"
  fi

  if [ -f "$CONF_ENV_FILE" ]; then
    cp "$CONF_ENV_FILE" "$snapshot_dir/$SNAPSHOT_ROOT_NAME/conf.env"
  elif [ -f "$LEGACY_DOCKER_ENV_FILE_PATH" ]; then
    split_env_file_to_paths "$LEGACY_DOCKER_ENV_FILE_PATH" \
      "$snapshot_dir/$SNAPSHOT_ROOT_NAME/access.env" \
      "$snapshot_dir/$SNAPSHOT_ROOT_NAME/conf.env"
  elif [ -f "$LEGACY_ROOT_ENV_FILE_PATH" ]; then
    split_env_file_to_paths "$LEGACY_ROOT_ENV_FILE_PATH" \
      "$snapshot_dir/$SNAPSHOT_ROOT_NAME/access.env" \
      "$snapshot_dir/$SNAPSHOT_ROOT_NAME/conf.env"
  fi

  if [ -f "$USAGE_LEDGER_FILE" ]; then
    mkdir -p "$snapshot_dir/$SNAPSHOT_ROOT_NAME/telemetry"
    cp "$USAGE_LEDGER_FILE" "$snapshot_dir/$SNAPSHOT_ROOT_NAME/telemetry/provider-usage.jsonl"
  fi

  if [ -f "$PROVIDER_HEALTH_FILE" ]; then
    mkdir -p "$snapshot_dir/$SNAPSHOT_ROOT_NAME/telemetry"
    cp "$PROVIDER_HEALTH_FILE" "$snapshot_dir/$SNAPSHOT_ROOT_NAME/telemetry/provider-health.json"
  fi

  if [ -f "$PROVIDER_BENCHMARKS_FILE" ]; then
    mkdir -p "$snapshot_dir/$SNAPSHOT_ROOT_NAME/telemetry"
    cp "$PROVIDER_BENCHMARKS_FILE" "$snapshot_dir/$SNAPSHOT_ROOT_NAME/telemetry/provider-benchmarks.json"
  fi

  if [ -f "$MEMORY_DIR/journal.jsonl" ]; then
    cp "$MEMORY_DIR/journal.jsonl" "$journal_path"
  fi

  if [ -d "$GATEWAY_STATE_DIR" ]; then
    mkdir -p "$snapshot_dir/$SNAPSHOT_ROOT_NAME/gateway"
    cp -R "$GATEWAY_STATE_DIR"/. "$snapshot_dir/$SNAPSHOT_ROOT_NAME/gateway/"
  fi

  if [ -d "$PROJECTIONS_DIR" ]; then
    mkdir -p "$snapshot_dir/$SNAPSHOT_ROOT_NAME/memory/projections"
    tar --exclude='*.migrated-*' -cf - -C "$PROJECTIONS_DIR" . | tar -xf - -C "$snapshot_dir/$SNAPSHOT_ROOT_NAME/memory/projections"
  fi

  if [ -f "$REVIEW_QUEUE_FILE" ] || [ -f "$CONTROL_LOG_FILE" ]; then
    mkdir -p "$snapshot_dir/$SNAPSHOT_ROOT_NAME/runtime"
    if [ -f "$REVIEW_QUEUE_FILE" ]; then
      cp "$REVIEW_QUEUE_FILE" "$snapshot_dir/$SNAPSHOT_ROOT_NAME/runtime/review-queue.jsonl"
    fi
    if [ -f "$CONTROL_LOG_FILE" ]; then
      cp "$CONTROL_LOG_FILE" "$snapshot_dir/$SNAPSHOT_ROOT_NAME/runtime/control-log.jsonl"
    fi
  fi

  if [ -d "$WORKCELLS_DIR" ]; then
    mkdir -p "$snapshot_dir/$SNAPSHOT_ROOT_NAME/runtime/workcells"
    tar --exclude='*.migrated-*' -cf - -C "$WORKCELLS_DIR" . | tar -xf - -C "$snapshot_dir/$SNAPSHOT_ROOT_NAME/runtime/workcells"
  fi

  if [ -f "$MEMORY_DIR/entries.jsonl" ]; then
    LOCAL_LLM_DIR="$STATE_DIR" python3 "$LOCAL_MEMORY_PY" export --compact --output "$compact_memory_path" >/dev/null
  fi

  cat > "$snapshot_dir/$SNAPSHOT_ROOT_NAME/manifest.json" <<EOF
{
  "created_at": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')",
  "state_dir": "$STATE_DIR",
  "access_env_present": $([ -f "$ACCESS_ENV_FILE" ] && echo true || echo false),
  "conf_env_present": $([ -f "$CONF_ENV_FILE" ] && echo true || echo false),
  "provider_routing_present": $([ -f "$PROVIDER_ROUTING_ENV_FILE" ] && echo true || echo false),
  "provider_registry_present": $([ -f "$PROVIDER_REGISTRY_FILE" ] && echo true || echo false),
  "capability_registry_present": $([ -f "$CAPABILITY_REGISTRY_FILE" ] && echo true || echo false),
  "memory_entries": $(wc -l < "$MEMORY_DIR/entries.jsonl" 2>/dev/null || echo 0),
  "journal_events": $(wc -l < "$MEMORY_DIR/journal.jsonl" 2>/dev/null || echo 0),
  "provider_usage_events": $(wc -l < "$USAGE_LEDGER_FILE" 2>/dev/null || echo 0),
  "review_queue_entries": $(wc -l < "$REVIEW_QUEUE_FILE" 2>/dev/null || echo 0),
  "control_log_entries": $(wc -l < "$CONTROL_LOG_FILE" 2>/dev/null || echo 0),
  "workcell_files": $(find "$WORKCELLS_DIR" -type f 2>/dev/null | wc -l || echo 0),
  "provider_health_present": $([ -f "$PROVIDER_HEALTH_FILE" ] && echo true || echo false),
  "provider_benchmarks_present": $([ -f "$PROVIDER_BENCHMARKS_FILE" ] && echo true || echo false),
  "memory_format": "hybrid-sqlite-compact-jsonl",
  "worker_model": "$(grep -E '^QWEN_MODEL=' "$LOCAL_LLM_ENV_FILE" 2>/dev/null | cut -d= -f2- || echo unknown)",
  "embed_model": "$(grep -E '^EMBED_MODEL=' "$LOCAL_LLM_ENV_FILE" 2>/dev/null | cut -d= -f2- || echo unknown)"
}
EOF
}

prune_backups() {
  local target_dir="$1"
  local prefix="$2"
  local keep="$3"

  ls -1t "$target_dir"/"${prefix}"-*.tar.gz 2>/dev/null | tail -n +"$((keep + 1))" | while read -r old_backup; do
    rm -f "$old_backup"
  done
}

save_backup() {
  local mode="$1"
  local target_dir
  local prefix
  local timestamp
  local temp_dir
  local archive_path

  require_state
  ensure_state_layout "$STATE_DIR"
  ensure_backup_dirs

  case "$mode" in
    hourly)
      target_dir="$HOURLY_DIR"
      prefix="$HOURLY_PREFIX"
      timestamp="$(date '+%Y-%m-%d_%H')"
      ;;
    daily)
      target_dir="$DAILY_DIR"
      prefix="$DAILY_PREFIX"
      timestamp="$(date '+%Y-%m-%d')"
      ;;
    *)
      usage
      exit 1
      ;;
  esac

  temp_dir="$(mktemp -d)"
  build_snapshot_dir "$temp_dir"

  archive_path="${target_dir}/${prefix}-${timestamp}.tar.gz"
  tar -czf "$archive_path" -C "$temp_dir" "$SNAPSHOT_ROOT_NAME"
  rm -rf "$temp_dir"

  if [ "$mode" = "hourly" ]; then
    prune_backups "$target_dir" "$prefix" "$KEEP_HOURLY"
  else
    prune_backups "$target_dir" "$prefix" "$KEEP_DAILY"
  fi

  log "Saved ${mode} Genie backup to ${archive_path}" "backup.log"
  echo "$archive_path"
}

restore_backup() {
  local backup_path="$1"
  local force_restore="${2:-}"
  local temp_dir
  local snapshot_dir
  local compact_memory_path
  local journal_memory_path
  local legacy_memory_path

  if [ ! -f "$backup_path" ]; then
    echo "Backup file not found: $backup_path"
    exit 1
  fi

  if [ "$force_restore" != "--force" ]; then
    echo "This will overwrite the current Genie state at $STATE_DIR"
    read -r -p "Continue? (yes/no): " reply
    if [[ ! "$reply" =~ ^[Yy][Ee][Ss]$ ]]; then
      echo "Restore cancelled"
      exit 0
    fi
  fi

  ensure_state_layout "$STATE_DIR"
  run_as_root mkdir -p "$MEMORY_DIR"
  run_as_root chown -R "$OWNER_USER:$OWNER_GROUP" "$STATE_DIR"
  temp_dir="$(mktemp -d)"
  tar -xzf "$backup_path" -C "$temp_dir"
  snapshot_dir="$temp_dir/$SNAPSHOT_ROOT_NAME"
  compact_memory_path="$snapshot_dir/memory/entries.compact.jsonl"
  journal_memory_path="$snapshot_dir/memory/journal.jsonl"
  legacy_memory_path="$snapshot_dir/memory/entries.jsonl"

  if [ ! -d "$snapshot_dir" ]; then
    rm -rf "$temp_dir"
    echo "Backup archive is missing ${SNAPSHOT_ROOT_NAME}"
    exit 1
  fi

  if [ -f "$snapshot_dir/policy/local-llm.env" ]; then
    run_as_root mkdir -p "$POLICY_DIR"
    run_as_root install -m 644 "$snapshot_dir/policy/local-llm.env" "$LOCAL_LLM_ENV_FILE"
  elif [ -f "$snapshot_dir/local-llm.env" ]; then
    run_as_root mkdir -p "$POLICY_DIR"
    run_as_root install -m 644 "$snapshot_dir/local-llm.env" "$LOCAL_LLM_ENV_FILE"
  fi

  if [ -f "$snapshot_dir/policy/genie-gateway.env" ]; then
    run_as_root mkdir -p "$POLICY_DIR"
    run_as_root install -m 600 "$snapshot_dir/policy/genie-gateway.env" "$GENIE_GATEWAY_ENV_FILE"
  elif [ -f "$snapshot_dir/genie-gateway.env" ]; then
    run_as_root mkdir -p "$POLICY_DIR"
    run_as_root install -m 600 "$snapshot_dir/genie-gateway.env" "$GENIE_GATEWAY_ENV_FILE"
  elif [ -f "$snapshot_dir/freewiller-gateway.env" ]; then
    run_as_root mkdir -p "$POLICY_DIR"
    run_as_root install -m 600 "$snapshot_dir/freewiller-gateway.env" "$GENIE_GATEWAY_ENV_FILE"
  fi

  if [ -f "$snapshot_dir/policy/provider-routing.env" ]; then
    run_as_root mkdir -p "$POLICY_DIR"
    run_as_root install -m 600 "$snapshot_dir/policy/provider-routing.env" "$PROVIDER_ROUTING_ENV_FILE"
  elif [ -f "$snapshot_dir/provider-routing.env" ]; then
    run_as_root mkdir -p "$POLICY_DIR"
    run_as_root install -m 600 "$snapshot_dir/provider-routing.env" "$PROVIDER_ROUTING_ENV_FILE"
  fi

  if [ -f "$snapshot_dir/policy/provider-registry.json" ]; then
    run_as_root mkdir -p "$POLICY_DIR"
    run_as_root install -m 644 "$snapshot_dir/policy/provider-registry.json" "$PROVIDER_REGISTRY_FILE"
  elif [ -f "$snapshot_dir/provider-registry.json" ]; then
    run_as_root mkdir -p "$POLICY_DIR"
    run_as_root install -m 644 "$snapshot_dir/provider-registry.json" "$PROVIDER_REGISTRY_FILE"
  fi

  if [ -f "$snapshot_dir/policy/capability-registry.json" ]; then
    run_as_root mkdir -p "$POLICY_DIR"
    run_as_root install -m 644 "$snapshot_dir/policy/capability-registry.json" "$CAPABILITY_REGISTRY_FILE"
  fi

  if [ -f "$snapshot_dir/access.env" ]; then
    run_as_root mkdir -p "$(dirname "$ACCESS_ENV_FILE")"
    run_as_root install -m 600 "$snapshot_dir/access.env" "$ACCESS_ENV_FILE"
    run_as_root chown "$OWNER_USER:$OWNER_GROUP" "$ACCESS_ENV_FILE"
  fi

  if [ -f "$snapshot_dir/conf.env" ]; then
    run_as_root mkdir -p "$(dirname "$CONF_ENV_FILE")"
    run_as_root install -m 600 "$snapshot_dir/conf.env" "$CONF_ENV_FILE"
    run_as_root chown "$OWNER_USER:$OWNER_GROUP" "$CONF_ENV_FILE"
  elif [ -f "$snapshot_dir/repo.env" ]; then
    run_as_root mkdir -p "$(dirname "$ACCESS_ENV_FILE")"
    split_env_file_to_paths "$snapshot_dir/repo.env" "$ACCESS_ENV_FILE" "$CONF_ENV_FILE"
    run_as_root chown "$OWNER_USER:$OWNER_GROUP" "$ACCESS_ENV_FILE" "$CONF_ENV_FILE"
    if [ -f "$LEGACY_DOCKER_ENV_FILE_PATH" ]; then
      run_as_root rm -f "$LEGACY_DOCKER_ENV_FILE_PATH"
    fi
    if [ -f "$LEGACY_ROOT_ENV_FILE_PATH" ]; then
      run_as_root rm -f "$LEGACY_ROOT_ENV_FILE_PATH"
    fi
  fi

  if [ -f "$snapshot_dir/telemetry/provider-usage.jsonl" ]; then
    run_as_root mkdir -p "$(dirname "$USAGE_LEDGER_FILE")"
    run_as_root install -m 644 "$snapshot_dir/telemetry/provider-usage.jsonl" "$USAGE_LEDGER_FILE"
  fi

  if [ -f "$snapshot_dir/telemetry/provider-health.json" ]; then
    run_as_root mkdir -p "$(dirname "$PROVIDER_HEALTH_FILE")"
    run_as_root install -m 644 "$snapshot_dir/telemetry/provider-health.json" "$PROVIDER_HEALTH_FILE"
  fi

  if [ -f "$snapshot_dir/telemetry/provider-benchmarks.json" ]; then
    run_as_root mkdir -p "$(dirname "$PROVIDER_BENCHMARKS_FILE")"
    run_as_root install -m 644 "$snapshot_dir/telemetry/provider-benchmarks.json" "$PROVIDER_BENCHMARKS_FILE"
  fi

  if [ -f "$journal_memory_path" ]; then
    run_as_root install -m 644 "$journal_memory_path" "$MEMORY_DIR/journal.jsonl"
  fi

  if [ -d "$snapshot_dir/gateway" ]; then
    run_as_root mkdir -p "$GATEWAY_STATE_DIR"
    run_as_root cp -R "$snapshot_dir/gateway"/. "$GATEWAY_STATE_DIR/"
  fi

  if [ -d "$snapshot_dir/memory/projections" ]; then
    run_as_root mkdir -p "$PROJECTIONS_DIR"
    run_as_root cp -R "$snapshot_dir/memory/projections"/. "$PROJECTIONS_DIR/"
  elif [ -d "$snapshot_dir/projections" ]; then
    run_as_root mkdir -p "$PROJECTIONS_DIR"
    run_as_root cp -R "$snapshot_dir/projections"/. "$PROJECTIONS_DIR/"
  fi

  if [ -f "$snapshot_dir/runtime/review-queue.jsonl" ]; then
    run_as_root mkdir -p "$RUNTIME_DIR"
    run_as_root install -m 644 "$snapshot_dir/runtime/review-queue.jsonl" "$REVIEW_QUEUE_FILE"
  fi

  if [ -f "$snapshot_dir/runtime/control-log.jsonl" ]; then
    run_as_root mkdir -p "$RUNTIME_DIR"
    run_as_root install -m 644 "$snapshot_dir/runtime/control-log.jsonl" "$CONTROL_LOG_FILE"
  fi

  if [ -d "$snapshot_dir/runtime/workcells" ]; then
    run_as_root mkdir -p "$WORKCELLS_DIR"
    run_as_root cp -R "$snapshot_dir/runtime/workcells"/. "$WORKCELLS_DIR/"
  fi

  if [ -f "$compact_memory_path" ]; then
    LOCAL_LLM_DIR="$STATE_DIR" python3 "$LOCAL_MEMORY_PY" import --input "$compact_memory_path" --replace >/dev/null
  elif [ -f "$legacy_memory_path" ]; then
    LOCAL_LLM_DIR="$STATE_DIR" python3 "$LOCAL_MEMORY_PY" import --input "$legacy_memory_path" --replace >/dev/null
  fi

  run_as_root chown -R "$OWNER_USER:$OWNER_GROUP" "$STATE_DIR"
  rm -rf "$temp_dir"

  log "Restored Genie state from ${backup_path}" "backup.log"
  echo "Restored from ${backup_path}"
}

list_backups() {
  local mode="${1:-all}"

  case "$mode" in
    hourly)
      ls -lh "$HOURLY_DIR"/*.tar.gz 2>/dev/null || echo "No hourly backups found."
      ;;
    daily)
      ls -lh "$DAILY_DIR"/*.tar.gz 2>/dev/null || echo "No daily backups found."
      ;;
    all)
      echo "Hourly:"
      ls -lh "$HOURLY_DIR"/*.tar.gz 2>/dev/null || echo "No hourly backups found."
      echo
      echo "Daily:"
      ls -lh "$DAILY_DIR"/*.tar.gz 2>/dev/null || echo "No daily backups found."
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

case "${1:-}" in
  save)
    save_backup "${2:-}"
    ;;
  restore)
    restore_backup "${2:-}" "${3:-}"
    ;;
  list)
    list_backups "${2:-all}"
    ;;
  *)
    usage
    exit 1
    ;;
esac
