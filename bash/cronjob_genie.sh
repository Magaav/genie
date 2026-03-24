#!/bin/bash

set -euo pipefail

source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/env.sh"

BACKUP_SCRIPT="$(realpath "$ROOT_DIR/bash/backup_genie.sh")"
CRON_LOG_DIR="$LOG_BASH_DIR"
HOURLY_CRON_LOG="$CRON_LOG_DIR/backup-hourly-cron.log"
DAILY_CRON_LOG="$CRON_LOG_DIR/backup-daily-cron.log"
HOURLY_CRON_ENTRY="5 * * * * $BACKUP_SCRIPT save hourly >> $HOURLY_CRON_LOG 2>&1"
DAILY_CRON_ENTRY="17 3 * * * $BACKUP_SCRIPT save daily >> $DAILY_CRON_LOG 2>&1"

root_crontab() {
  if [ "${EUID:-$(id -u)}" -eq 0 ]; then
    crontab "$@"
  else
    sudo crontab "$@"
  fi
}

filter_backup_entries() {
  local current_entries
  local filtered_entries

  current_entries="$(root_crontab -l 2>/dev/null || true)"
  filtered_entries="$current_entries"

  filtered_entries="$(printf '%s\n' "$filtered_entries" | grep -Ev 'backup_(freewiller|genie)\.sh save (hourly|daily)' || true)"
  filtered_entries="$(printf '%s\n' "$filtered_entries" | grep -Ev '/backup-(hourly|daily)-cron\.log' || true)"
  printf '%s\n' "$filtered_entries"
}

rewrite_backup_entries() {
  {
    filter_backup_entries | sed '/^$/d'
    echo "$HOURLY_CRON_ENTRY"
    echo "$DAILY_CRON_ENTRY"
  } | root_crontab -
}

main() {
  run_as_root mkdir -p "$CRON_LOG_DIR"
  chmod +x "$BACKUP_SCRIPT"

  rewrite_backup_entries

  echo "Installed Genie backup cron jobs."
  echo "Hourly: $HOURLY_CRON_ENTRY"
  echo "Daily:  $DAILY_CRON_ENTRY"
  echo
  echo "Current root crontab entries:"
  root_crontab -l | grep -v "^#" | grep -v "^$" || echo "(no entries)"
}

main "$@"
