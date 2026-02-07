#!/bin/bash

# Get Bash Variables
source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/env.sh"

echo "=========================================="
echo "Starting OpenClaw Gateway"
echo "=========================================="
echo ""

sudo mkdir -p /root/.openclaw
sudo cp /local/openclaw/openclaw.json /root/.openclaw/openclaw.json

# Try to find Bun in common locations
if [ -f "$HOME/.bun/bin/bun" ]; then
  export BUN_INSTALL="$HOME/.bun"
  export PATH="$BUN_INSTALL/bin:$PATH"
elif [ -n "$SUDO_USER" ]; then
  ACTUAL_USER_HOME=$(getent passwd "$SUDO_USER" | cut -d: -f6)
  if [ -f "$ACTUAL_USER_HOME/.bun/bin/bun" ]; then
    export BUN_INSTALL="$ACTUAL_USER_HOME/.bun"
    export PATH="$BUN_INSTALL/bin:$PATH"
  fi
fi

# Check if Bun is accessible
if ! command -v bun &> /dev/null; then
  echo "ERROR: Bun is not installed or not in PATH"
  exit 1
fi

OPENCLAW_DIR="$ROOT_DIR/openclaw"

# Check if openclaw directory exists
if [ ! -d "$OPENCLAW_DIR" ]; then
  echo "ERROR: OpenClaw directory not found at $OPENCLAW_DIR"
  echo "Please run ./bash/install_openclaw.sh first"
  exit 1
fi

cd "$OPENCLAW_DIR" || exit 1

# Sync config to root directory if it exists
if [ -f "$OPENCLAW_DIR/openclaw.json" ]; then
  echo "Syncing config to root state directory..."
  mkdir -p /root/.openclaw
  cp "$OPENCLAW_DIR/openclaw.json" /root/.openclaw/openclaw.json
  echo "✓ Config synced"
fi

# Check if already running and stop it
if pgrep -f "openclaw gateway" > /dev/null; then
  echo "Stopping existing gateway..."
  pkill -9 -f "openclaw gateway"
  pkill -f "openclaw gateway"
  fuser -k 18789/tcp 2>/dev/null
  sleep 2
  echo "✓ Existing gateway stopped"
fi

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

echo "Starting OpenClaw Gateway..."
echo "  Reading configuration from openclaw.json"
echo "  Log: $LOG_DIR/openclaw-gateway.log"
echo ""

# Start gateway in background
nohup bun run openclaw gateway --verbose > "$LOG_DIR/openclaw-gateway.log" 2>&1 &

GATEWAY_PID=$!

# Wait a moment for startup
sleep 3

# Check if process is still running
if ps -p $GATEWAY_PID > /dev/null; then
  echo "✓ Gateway started successfully (PID: $GATEWAY_PID)"
  echo ""
  echo "Check logs: tail -f $LOG_DIR/openclaw-gateway.log"
  echo "Check status: ps aux | grep openclaw"
  echo "Stop gateway: sudo bash /local/bash/start_gateway.sh stop"
  echo ""
  
  # Wait another moment and check if listening on port
  sleep 2
  if ss -tlnp 2>/dev/null | grep -q ":18789" || netstat -tlnp 2>/dev/null | grep -q ":18789"; then
    echo "✓ Gateway is listening on port 18789"
    log "OpenClaw gateway started successfully on port 18789"
  else
    echo "WARNING: Gateway process running but not listening on port 18789"
    echo "Check the logs for errors: tail -f $LOG_DIR/openclaw-gateway.log"
  fi
else
  echo "ERROR: Gateway failed to start"
  echo "Check the logs: tail -f $LOG_DIR/openclaw-gateway.log"
  log "ERROR: OpenClaw gateway failed to start" "error.log"
  exit 1
fi

exit 0