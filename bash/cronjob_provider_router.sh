#!/bin/bash

set -euo pipefail

source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/env.sh"

ROUTER_SCRIPT="$(realpath "$ROOT_DIR/bash/provider_router.py")"
CRON_LOG_DIR="$LOG_BASH_DIR"
HEARTBEAT_CRON_LOG="$CRON_LOG_DIR/provider-heartbeat-cron.log"
EVALUATE_CRON_LOG="$CRON_LOG_DIR/provider-evaluate-cron.log"
JUDGE_CRON_LOG="$CRON_LOG_DIR/provider-judge-cron.log"
SCORECARD_CRON_LOG="$CRON_LOG_DIR/provider-scorecards-cron.log"
HEARTBEAT_CRON_MARKER="provider_router.py heartbeat"
EVALUATE_CRON_MARKER="provider_router.py evaluate --judge-mode never"
JUDGE_CRON_MARKER="provider_router.py evaluate --judge-mode targeted"
SCORECARD_CRON_MARKER="provider_router.py scorecards --refresh"
HEARTBEAT_CRON_ENTRY="*/10 * * * * python3 $ROUTER_SCRIPT heartbeat >> $HEARTBEAT_CRON_LOG 2>&1"
EVALUATE_CRON_ENTRY="13 */6 * * * python3 $ROUTER_SCRIPT evaluate --judge-mode never >> $EVALUATE_CRON_LOG 2>&1"
JUDGE_CRON_ENTRY="27 4 * * * python3 $ROUTER_SCRIPT evaluate --judge-mode targeted >> $JUDGE_CRON_LOG 2>&1"
SCORECARD_CRON_ENTRY="43 * * * * python3 $ROUTER_SCRIPT scorecards --refresh >> $SCORECARD_CRON_LOG 2>&1"

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
  chmod +x "$ROUTER_SCRIPT"

  upsert_cron_entry "$HEARTBEAT_CRON_ENTRY" "$HEARTBEAT_CRON_MARKER"
  upsert_cron_entry "$EVALUATE_CRON_ENTRY" "$EVALUATE_CRON_MARKER"
  upsert_cron_entry "$JUDGE_CRON_ENTRY" "$JUDGE_CRON_MARKER"
  upsert_cron_entry "$SCORECARD_CRON_ENTRY" "$SCORECARD_CRON_MARKER"

  echo "Installed Freewiller provider routing cron jobs."
  echo "Heartbeat: $HEARTBEAT_CRON_ENTRY"
  echo "Evaluate:  $EVALUATE_CRON_ENTRY"
  echo "Judge:     $JUDGE_CRON_ENTRY"
  echo "Scorecard: $SCORECARD_CRON_ENTRY"
  echo
  echo "Current root crontab entries:"
  root_crontab -l | grep -v "^#" | grep -v "^$" || echo "(no entries)"
}

main "$@"
