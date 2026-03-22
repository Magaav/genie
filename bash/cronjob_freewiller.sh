#!/bin/bash

set -euo pipefail

source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/env.sh"

BACKUP_SCRIPT="$(realpath "$ROOT_DIR/bash/backup_freewiller.sh")"
CRON_LOG_DIR="$LOG_BASH_DIR"
HOURLY_CRON_LOG="$CRON_LOG_DIR/backup-hourly-cron.log"
DAILY_CRON_LOG="$CRON_LOG_DIR/backup-daily-cron.log"
HOURLY_CRON_MARKER="backup_freewiller.sh save hourly"
DAILY_CRON_MARKER="backup_freewiller.sh save daily"
HOURLY_CRON_ENTRY="5 * * * * $BACKUP_SCRIPT save hourly >> $HOURLY_CRON_LOG 2>&1"
DAILY_CRON_ENTRY="17 3 * * * $BACKUP_SCRIPT save daily >> $DAILY_CRON_LOG 2>&1"

root_crontab() {
  if [ "${EUID:-$(id -u)}" -eq 0 ]; then
    crontab "$@"
  else
    sudo crontab "$@"
  fi
}

upsert_cron_entry() {
  local entry="$1"
  local marker="$2"
  local current_entries
  local filtered_entries

  current_entries="$(root_crontab -l 2>/dev/null || true)"
  filtered_entries="$(printf '%s\n' "$current_entries" | grep -Fv "$marker" || true)"

  {
    printf '%s\n' "$filtered_entries" | sed '/^$/d'
    echo "$entry"
  } | root_crontab -
}

main() {
  run_as_root mkdir -p "$CRON_LOG_DIR"
  chmod +x "$BACKUP_SCRIPT"

  upsert_cron_entry "$HOURLY_CRON_ENTRY" "$HOURLY_CRON_MARKER"
  upsert_cron_entry "$DAILY_CRON_ENTRY" "$DAILY_CRON_MARKER"

  echo "Installed Freewiller backup cron jobs."
  echo "Hourly: $HOURLY_CRON_ENTRY"
  echo "Daily:  $DAILY_CRON_ENTRY"
  echo
  echo "Current root crontab entries:"
  root_crontab -l | grep -v "^#" | grep -v "^$" || echo "(no entries)"
}

main "$@"
