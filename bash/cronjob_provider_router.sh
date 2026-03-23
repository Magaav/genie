#!/bin/bash

set -euo pipefail

source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/env.sh"

GATEWAY_URL="${GATEWAY_URL:-http://127.0.0.1:${GENIE_GATEWAY_PORT:-18790}}"
CRON_LOG_DIR="$LOG_BASH_DIR"
HEARTBEAT_CRON_LOG="$CRON_LOG_DIR/provider-heartbeat-cron.log"
EVALUATE_CRON_LOG="$CRON_LOG_DIR/provider-evaluate-cron.log"
JUDGE_CRON_LOG="$CRON_LOG_DIR/provider-judge-cron.log"
SCORECARD_CRON_LOG="$CRON_LOG_DIR/provider-scorecards-cron.log"
DISCOVERY_CRON_LOG="$CRON_LOG_DIR/provider-discovery-cron.log"
HEARTBEAT_CRON_MARKER="/providers/health?refresh=1"
EVALUATE_CRON_MARKER="/providers/evaluate.*judge_mode\":\"never"
JUDGE_CRON_MARKER="/providers/evaluate.*judge_mode\":\"targeted"
SCORECARD_CRON_MARKER="/providers/scorecards?refresh=1"
DISCOVERY_CRON_MARKER="/providers/discover.*provider_family\":\"all"
HEARTBEAT_CRON_ENTRY="*/10 * * * * curl -fsS \"$GATEWAY_URL/providers/health?refresh=1\" >> $HEARTBEAT_CRON_LOG 2>&1"
EVALUATE_CRON_ENTRY="13 */6 * * * curl -fsS -X POST -H 'Content-Type: application/json' -d '{\"judge_mode\":\"never\"}' \"$GATEWAY_URL/providers/evaluate\" >> $EVALUATE_CRON_LOG 2>&1"
JUDGE_CRON_ENTRY="27 4 * * * curl -fsS -X POST -H 'Content-Type: application/json' -d '{\"judge_mode\":\"targeted\"}' \"$GATEWAY_URL/providers/evaluate\" >> $JUDGE_CRON_LOG 2>&1"
SCORECARD_CRON_ENTRY="43 * * * * curl -fsS \"$GATEWAY_URL/providers/scorecards?refresh=1\" >> $SCORECARD_CRON_LOG 2>&1"
DISCOVERY_CRON_ENTRY="9 2 * * * curl -fsS -X POST -H 'Content-Type: application/json' -d '{\"provider_family\":\"all\",\"sync\":true}' \"$GATEWAY_URL/providers/discover\" >> $DISCOVERY_CRON_LOG 2>&1"

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
  upsert_cron_entry "$HEARTBEAT_CRON_ENTRY" "$HEARTBEAT_CRON_MARKER"
  upsert_cron_entry "$EVALUATE_CRON_ENTRY" "$EVALUATE_CRON_MARKER"
  upsert_cron_entry "$JUDGE_CRON_ENTRY" "$JUDGE_CRON_MARKER"
  upsert_cron_entry "$SCORECARD_CRON_ENTRY" "$SCORECARD_CRON_MARKER"
  upsert_cron_entry "$DISCOVERY_CRON_ENTRY" "$DISCOVERY_CRON_MARKER"

  echo "Installed Genie provider routing cron jobs."
  echo "Heartbeat: $HEARTBEAT_CRON_ENTRY"
  echo "Evaluate:  $EVALUATE_CRON_ENTRY"
  echo "Judge:     $JUDGE_CRON_ENTRY"
  echo "Scorecard: $SCORECARD_CRON_ENTRY"
  echo "Discovery: $DISCOVERY_CRON_ENTRY"
  echo
  echo "Current root crontab entries:"
  root_crontab -l | grep -v "^#" | grep -v "^$" || echo "(no entries)"
}

main "$@"
