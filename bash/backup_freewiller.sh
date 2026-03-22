#!/bin/bash

set -euo pipefail

source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/env.sh"

STATE_DIR="${LOCAL_LLM_DIR:-$(resolve_state_dir)}"
BACKUP_ROOT="${BACKUP_ROOT:-/local/backups}"
HOURLY_DIR="${BACKUP_ROOT}/hourly"
DAILY_DIR="${BACKUP_ROOT}/daily"
SNAPSHOT_ROOT_NAME="freewiller-state"
HOURLY_PREFIX="freewiller-hourly"
DAILY_PREFIX="freewiller-daily"
KEEP_HOURLY="${KEEP_HOURLY:-3}"
KEEP_DAILY="${KEEP_DAILY:-1}"
LOCAL_MEMORY_PY="$(realpath "$ROOT_DIR/bash/local_memory.py")"
REPO_ENV_FILE="${REPO_ENV_FILE:-$ROOT_DIR/.env}"

if [ "${EUID:-$(id -u)}" -eq 0 ]; then
  OWNER_USER="${FREEWILLER_OWNER:-${SUDO_USER:-ubuntu}}"
else
  OWNER_USER="${FREEWILLER_OWNER:-$USER}"
fi
OWNER_GROUP="$(id -gn "$OWNER_USER" 2>/dev/null || echo "$OWNER_USER")"

usage() {
  cat <<'EOF'
Usage:
  backup_freewiller.sh save {hourly|daily}
  backup_freewiller.sh restore <backup-file> [--force]
  backup_freewiller.sh list [hourly|daily|all]
EOF
}

ensure_backup_dirs() {
  run_as_root mkdir -p "$HOURLY_DIR" "$DAILY_DIR"
  run_as_root chown -R "$OWNER_USER:$OWNER_GROUP" "$BACKUP_ROOT"
}

require_state() {
  if [ ! -d "$STATE_DIR" ]; then
    echo "Freewiller state directory not found at $STATE_DIR"
    exit 1
  fi
}

build_snapshot_dir() {
  local snapshot_dir="$1"
  local compact_memory_path="$snapshot_dir/$SNAPSHOT_ROOT_NAME/memory/entries.compact.jsonl"
  local journal_path="$snapshot_dir/$SNAPSHOT_ROOT_NAME/memory/journal.jsonl"

  mkdir -p "$snapshot_dir/$SNAPSHOT_ROOT_NAME/memory"

  if [ -f "$STATE_DIR/local-llm.env" ]; then
    cp "$STATE_DIR/local-llm.env" "$snapshot_dir/$SNAPSHOT_ROOT_NAME/local-llm.env"
  fi

  if [ -f "$STATE_DIR/freewiller-gateway.env" ]; then
    cp "$STATE_DIR/freewiller-gateway.env" "$snapshot_dir/$SNAPSHOT_ROOT_NAME/freewiller-gateway.env"
  fi

  if [ -f "$REPO_ENV_FILE" ]; then
    cp "$REPO_ENV_FILE" "$snapshot_dir/$SNAPSHOT_ROOT_NAME/repo.env"
  fi

  if [ -f "$STATE_DIR/memory/journal.jsonl" ]; then
    cp "$STATE_DIR/memory/journal.jsonl" "$journal_path"
  fi

  if [ -f "$STATE_DIR/memory/entries.jsonl" ]; then
    LOCAL_LLM_DIR="$STATE_DIR" python3 "$LOCAL_MEMORY_PY" export --compact --output "$compact_memory_path" >/dev/null
  fi

  cat > "$snapshot_dir/$SNAPSHOT_ROOT_NAME/manifest.json" <<EOF
{
  "created_at": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')",
  "state_dir": "$STATE_DIR",
  "repo_env_present": $([ -f "$REPO_ENV_FILE" ] && echo true || echo false),
  "memory_entries": $(wc -l < "$STATE_DIR/memory/entries.jsonl" 2>/dev/null || echo 0),
  "journal_events": $(wc -l < "$STATE_DIR/memory/journal.jsonl" 2>/dev/null || echo 0),
  "memory_format": "hybrid-sqlite-compact-jsonl",
  "worker_model": "$(grep -E '^QWEN_MODEL=' "$STATE_DIR/local-llm.env" 2>/dev/null | cut -d= -f2- || echo unknown)",
  "embed_model": "$(grep -E '^EMBED_MODEL=' "$STATE_DIR/local-llm.env" 2>/dev/null | cut -d= -f2- || echo unknown)"
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

  log "Saved ${mode} Freewiller backup to ${archive_path}" "backup.log"
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
    echo "This will overwrite the current Freewiller state at $STATE_DIR"
    read -r -p "Continue? (yes/no): " reply
    if [[ ! "$reply" =~ ^[Yy][Ee][Ss]$ ]]; then
      echo "Restore cancelled"
      exit 0
    fi
  fi

  run_as_root mkdir -p "$STATE_DIR/memory"
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

  if [ -f "$snapshot_dir/local-llm.env" ]; then
    run_as_root install -m 644 "$snapshot_dir/local-llm.env" "$STATE_DIR/local-llm.env"
  fi

  if [ -f "$snapshot_dir/freewiller-gateway.env" ]; then
    run_as_root install -m 600 "$snapshot_dir/freewiller-gateway.env" "$STATE_DIR/freewiller-gateway.env"
  fi

  if [ -f "$snapshot_dir/repo.env" ]; then
    run_as_root install -m 600 "$snapshot_dir/repo.env" "$REPO_ENV_FILE"
    run_as_root chown "$OWNER_USER:$OWNER_GROUP" "$REPO_ENV_FILE"
  fi

  if [ -f "$journal_memory_path" ]; then
    run_as_root install -m 644 "$journal_memory_path" "$STATE_DIR/memory/journal.jsonl"
  fi

  if [ -f "$compact_memory_path" ]; then
    LOCAL_LLM_DIR="$STATE_DIR" python3 "$LOCAL_MEMORY_PY" import --input "$compact_memory_path" --replace >/dev/null
  elif [ -f "$legacy_memory_path" ]; then
    LOCAL_LLM_DIR="$STATE_DIR" python3 "$LOCAL_MEMORY_PY" import --input "$legacy_memory_path" --replace >/dev/null
  fi

  run_as_root chown -R "$OWNER_USER:$OWNER_GROUP" "$STATE_DIR"
  rm -rf "$temp_dir"

  log "Restored Freewiller state from ${backup_path}" "backup.log"
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
