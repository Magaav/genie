#!/bin/bash

# Setup daily OpenClaw backup cron job
# Runs every day at 3 AM

set -e

# Get Bash Variables
source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/env.sh"
BACKUP_SCRIPT="$ROOT_DIR/bash/backup_openclaw.sh"

echo "Setting up OpenClaw automated backup..."
echo "ROOT_DIR: $ROOT_DIR"
echo "BACKUP_SCRIPT: $BACKUP_SCRIPT"

# Make backup script executable
chmod +x "$BACKUP_SCRIPT"
echo "✓ Made backup script executable"

# Create cron job entry with fully expanded path
CRON_ENTRY="* * * * * $BACKUP_SCRIPT save >> /local/log/system/backup-cron.log 2>&1"

echo "Cron entry to add: $CRON_ENTRY"

# Check if cron job already exists
if sudo crontab -l 2>/dev/null | grep -F "$BACKUP_SCRIPT save" >/dev/null; then
  echo "! Backup cron job already exists"
else
  # Add to root crontab (uses sudo to handle permission issues)
  (sudo crontab -l 2>/dev/null; echo "$CRON_ENTRY") | sudo crontab -
  echo "✓ Added daily backup to root crontab (runs at 3 AM)"
fi

# Display current crontab
echo ""
echo "Current root crontab entries:"
sudo crontab -l | grep -v "^#" | grep -v "^$" || echo "(no entries)"

echo ""
echo "✓ Setup completed!"
echo ""
echo "The backup will run daily at 3 AM and save to: /local/backup/"
echo "Logs will be written to: /local/log/system/backup-cron.log"
echo ""
echo "To manually run a backup now:"
echo "  $BACKUP_SCRIPT save"