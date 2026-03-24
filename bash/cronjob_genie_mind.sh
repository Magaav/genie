#!/bin/bash

set -euo pipefail

source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/env.sh"

ETHICS_URL="${ETHICS_URL:-http://127.0.0.1:${GENIE_ETHICS_PORT:-18791}}"
CRON_LOG_DIR="$LOG_BASH_DIR"
MIND_CRON_LOG="$CRON_LOG_DIR/genie-mind-cron.log"
MIND_CRON_ENTRY="*/20 * * * * curl -fsS -X POST -H 'Content-Type: application/json' -d '{}' \"$ETHICS_URL/mind/run\" >> $MIND_CRON_LOG 2>&1"

root_crontab() {
  if [ "${EUID:-$(id -u)}" -eq 0 ]; then
    crontab "$@"
  else
    sudo crontab "$@"
  fi
}

rewrite_mind_entries() {
  local current_entries
  local filtered_entries

  current_entries="$(root_crontab -l 2>/dev/null || true)"
  filtered_entries="$(printf '%s\n' "$current_entries" | grep -Ev '/mind/run|genie-mind-cron\.log' || true)"

  {
    printf '%s\n' "$filtered_entries" | sed '/^$/d'
    echo "$MIND_CRON_ENTRY"
  } | root_crontab -
}

main() {
  run_as_root mkdir -p "$CRON_LOG_DIR"
  rewrite_mind_entries

  echo "Installed Genie mind cron jobs."
  echo "Mind: $MIND_CRON_ENTRY"
  echo
  echo "Current root crontab entries:"
  root_crontab -l | grep -v "^#" | grep -v "^$" || echo "(no entries)"
}

main "$@"
