#!/bin/bash

# OpenClaw Backup and Restore Script
# Handles critical configuration and state backup/restore

set -e  # Exit on any error

# Get Bash Variables
source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/env.sh"

# Backup configuration
BACKUP_DIR="/local/backup"
OPENCLAW_DIR="/local/.openclaw"
BACKUP_PREFIX="openclaw-backup"
MAX_BACKUPS=7  # Keep last 7 backups

save() {
  log "Starting OpenClaw backup..." "backup.log"
  
  # Create backup directory if it doesn't exist
  mkdir -p "$BACKUP_DIR"
  
  # Verify source directory exists
  if [ ! -d "$OPENCLAW_DIR" ]; then
    log "ERROR: OpenClaw directory not found at $OPENCLAW_DIR" "backup.log"
    echo "ERROR: OpenClaw directory not found at $OPENCLAW_DIR"
    exit 1
  fi
  
  # Generate timestamp-based backup filename
  TIMESTAMP=$(date '+%Y-%m-%d_%H-%M-%S')
  BACKUP_FILE="${BACKUP_DIR}/${BACKUP_PREFIX}_${TIMESTAMP}.tar.gz"
  
  log "Creating backup archive: $BACKUP_FILE" "backup.log"
  echo "Creating backup of $OPENCLAW_DIR..."
  
  # Create tarball of critical OpenClaw files
  # Exclude large/temporary files that aren't needed for restore
  tar -czf "$BACKUP_FILE" \
    --exclude='*/node_modules' \
    --exclude='*/sessions' \
    --exclude='*/logs' \
    --exclude='*/.cache' \
    --exclude='*/tmp' \
    -C /local .openclaw
  
  # Verify backup was created successfully
  if [ ! -f "$BACKUP_FILE" ]; then
    log "ERROR: Backup file was not created" "backup.log"
    echo "ERROR: Backup failed"
    exit 1
  fi
  
  BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
  log "Backup created successfully: $BACKUP_FILE ($BACKUP_SIZE)" "backup.log"
  echo "✓ Backup created: $BACKUP_FILE ($BACKUP_SIZE)"
  
  # Clean up old backups, keeping only the most recent ones
  log "Cleaning up old backups (keeping last $MAX_BACKUPS)..." "backup.log"
  
  # List all backup files sorted by modification time, newest first
  # Then remove all but the most recent MAX_BACKUPS files
  ls -t "$BACKUP_DIR"/${BACKUP_PREFIX}_*.tar.gz 2>/dev/null | tail -n +$((MAX_BACKUPS + 1)) | while read old_backup; do
    log "Removing old backup: $old_backup" "backup.log"
    echo "Removing old backup: $(basename "$old_backup")"
    rm -f "$old_backup"
  done
  
  log "Backup completed successfully" "backup.log"
  echo "✓ Backup completed successfully"
  
  # List current backups
  echo ""
  echo "Current backups:"
  ls -lh "$BACKUP_DIR"/${BACKUP_PREFIX}_*.tar.gz 2>/dev/null || echo "No backups found"
}

load() {
  local BACKUP_TO_RESTORE="$1"
  
  if [ -z "$BACKUP_TO_RESTORE" ]; then
    echo "ERROR: Please specify a backup file to restore"
    echo "Usage: $0 load <backup-filename>"
    echo ""
    echo "Available backups:"
    ls -lh "$BACKUP_DIR"/${BACKUP_PREFIX}_*.tar.gz 2>/dev/null || echo "No backups found"
    exit 1
  fi
  
  # Check if absolute path or just filename
  if [[ "$BACKUP_TO_RESTORE" == /* ]]; then
    BACKUP_PATH="$BACKUP_TO_RESTORE"
  else
    BACKUP_PATH="${BACKUP_DIR}/${BACKUP_TO_RESTORE}"
  fi
  
  # Verify backup file exists
  if [ ! -f "$BACKUP_PATH" ]; then
    log "ERROR: Backup file not found: $BACKUP_PATH" "backup.log"
    echo "ERROR: Backup file not found: $BACKUP_PATH"
    echo ""
    echo "Available backups:"
    ls -lh "$BACKUP_DIR"/${BACKUP_PREFIX}_*.tar.gz 2>/dev/null || echo "No backups found"
    exit 1
  fi
  
  log "Starting OpenClaw restore from: $BACKUP_PATH" "backup.log"
  echo "WARNING: This will overwrite the current OpenClaw configuration!"
  echo "Backup file: $BACKUP_PATH"
  echo ""
  read -p "Are you sure you want to continue? (yes/no): " -r
  
  if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo "Restore cancelled"
    log "Restore cancelled by user" "backup.log"
    exit 0
  fi
  
  # Stop OpenClaw gateway if running
  echo "Stopping OpenClaw gateway..."
  log "Stopping OpenClaw gateway before restore" "backup.log"
  cd /local/openclaw
  docker compose down openclaw-gateway 2>/dev/null || true
  
  # Backup current state before overwriting (safety measure)
  if [ -d "$OPENCLAW_DIR" ]; then
    SAFETY_BACKUP="${BACKUP_DIR}/pre-restore-backup_$(date '+%Y-%m-%d_%H-%M-%S').tar.gz"
    log "Creating safety backup of current state: $SAFETY_BACKUP" "backup.log"
    echo "Creating safety backup of current state..."
    tar -czf "$SAFETY_BACKUP" -C /local .openclaw
    echo "✓ Safety backup created: $SAFETY_BACKUP"
  fi
  
  # Remove current .openclaw directory
  log "Removing current OpenClaw directory" "backup.log"
  echo "Removing current configuration..."
  rm -rf "$OPENCLAW_DIR"
  
  # Extract backup
  log "Extracting backup: $BACKUP_PATH" "backup.log"
  echo "Extracting backup..."
  tar -xzf "$BACKUP_PATH" -C /local
  
  # Fix ownership (match Docker node user UID:GID 1000:1000)
  log "Fixing ownership (1000:1000)" "backup.log"
  echo "Fixing ownership..."
  sudo chown -R 1000:1000 "$OPENCLAW_DIR"
  
  # Fix permissions
  log "Fixing permissions" "backup.log"
  echo "Fixing permissions..."
  sudo chmod -R 755 "$OPENCLAW_DIR"
  
  log "Restore completed successfully" "backup.log"
  echo "✓ Restore completed successfully"
  echo ""
  echo "You can now start OpenClaw gateway:"
  echo "  cd /local/openclaw"
  echo "  docker compose up -d openclaw-gateway"
}

# Main script logic
case "$1" in
  save)
    save
    ;;
  load)
    load "$2"
    ;;
  list)
    echo "Available backups:"
    ls -lh "$BACKUP_DIR"/${BACKUP_PREFIX}_*.tar.gz 2>/dev/null || echo "No backups found"
    ;;
  *)
    echo "OpenClaw Backup & Restore Utility"
    echo ""
    echo "Usage: $0 {save|load|list}"
    echo ""
    echo "Commands:"
    echo "  save              Create a new backup"
    echo "  load <filename>   Restore from a specific backup"
    echo "  list              List available backups"
    echo ""
    echo "Examples:"
    echo "  $0 save"
    echo "  $0 load openclaw-backup_2026-01-15_03-00-00.tar.gz"
    echo "  $0 list"
    exit 1
    ;;
esac