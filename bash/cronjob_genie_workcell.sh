#!/bin/bash

set -euo pipefail

source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/env.sh"

ETHICS_URL="${ETHICS_URL:-http://127.0.0.1:${GENIE_ETHICS_PORT:-18791}}"
CRON_LOG_DIR="$LOG_BASH_DIR"
PROCESS_CRON_LOG="$CRON_LOG_DIR/genie-workcell-cron.log"
PROCESS_CRON_ENTRY="*/12 * * * * curl -fsS -X POST -H 'Content-Type: application/json' -d '{\"limit\":2}' \"$ETHICS_URL/process-queue\" >> $PROCESS_CRON_LOG 2>&1"

root_crontab() {
  if [ "${EUID:-$(id -u)}" -eq 0 ]; then
    crontab "$@"
  else
    sudo crontab "$@"
  fi
}

rewrite_workcell_entries() {
  local current_entries
  local filtered_entries

  current_entries="$(root_crontab -l 2>/dev/null || true)"
  filtered_entries="$(printf '%s\n' "$current_entries" | grep -Ev '/process-queue|genie-workcell-cron\.log' || true)"

  {
    printf '%s\n' "$filtered_entries" | sed '/^$/d'
    echo "$PROCESS_CRON_ENTRY"
  } | root_crontab -
}

main() {
  run_as_root mkdir -p "$CRON_LOG_DIR"
  rewrite_workcell_entries

  echo "Installed Genie workcell cron jobs."
  echo "Process: $PROCESS_CRON_ENTRY"
  echo
  echo "Current root crontab entries:"
  root_crontab -l | grep -v "^#" | grep -v "^$" || echo "(no entries)"
}

main "$@"
