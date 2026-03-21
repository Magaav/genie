#!/bin/bash

# Setup daily OpenClaw backup cron job
# Runs every day at 3 AM

set -e

# Get Bash Variables
source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/env.sh"
BACKUP_SCRIPT="$ROOT_DIR/bash/backup_openclaw.sh"
CRON_LOG="/local/log/system/backup-cron.log"

echo "Setting up OpenClaw automated backup..."
echo "ROOT_DIR: $ROOT_DIR"
echo "BACKUP_SCRIPT: $BACKUP_SCRIPT"

mkdir -p "$(dirname "$CRON_LOG")"
chmod +x "$BACKUP_SCRIPT"
echo "Made backup script executable"

CRON_ENTRY="0 3 * * * $BACKUP_SCRIPT save >> $CRON_LOG 2>&1"

echo "Cron entry to add: $CRON_ENTRY"

if sudo crontab -l 2>/dev/null | grep -F "$BACKUP_SCRIPT save" >/dev/null; then
  echo "Backup cron job already exists"
else
  (sudo crontab -l 2>/dev/null; echo "$CRON_ENTRY") | sudo crontab -
  echo "Added daily backup to root crontab (runs at 3 AM)"
fi

echo ""
echo "Current root crontab entries:"
sudo crontab -l | grep -v "^#" | grep -v "^$" || echo "(no entries)"

echo ""
echo "Setup completed"
echo ""
echo "The backup will run daily at 3 AM and save to: /local/backup/"
echo "Logs will be written to: $CRON_LOG"
echo ""
echo "To manually run a backup now:"
echo "  $BACKUP_SCRIPT save"
