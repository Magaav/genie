#!/bin/bash

# Get Bash Variables
source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/env.sh"

OPENCLAW_DIR="$ROOT_DIR/openclaw"

# Try to find Bun in common locations
if [ -f "$HOME/.bun/bin/bun" ]; then
  export BUN_INSTALL="$HOME/.bun"
  export PATH="$BUN_INSTALL/bin:$PATH"
elif [ -f "/root/.bun/bin/bun" ]; then
  export BUN_INSTALL="/root/.bun"
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

# Check if openclaw directory exists
if [ ! -d "$OPENCLAW_DIR" ]; then
  echo "ERROR: OpenClaw directory not found at $OPENCLAW_DIR"
  exit 1
fi

cd "$OPENCLAW_DIR" || exit 1

# Parse command
COMMAND="${1:-list}"
CHANNEL="${2:-webchat}"

case "$COMMAND" in
  list|ls)
    if [ "$2" != "" ]; then
      CHANNEL="$2"
    fi
    
    echo "=========================================="
    echo "OpenClaw Pairing Codes ($CHANNEL)"
    echo "=========================================="
    echo ""
    bun run openclaw pairing list --channel "$CHANNEL"
    ;;
    
  list-all)
    echo "=========================================="
    echo "OpenClaw Pairing Codes (All Channels)"
    echo "=========================================="
    echo ""
    for chan in webchat telegram whatsapp discord signal slack; do
      echo ""
      echo "--- $chan ---"
      bun run openclaw pairing list --channel "$chan" 2>/dev/null || echo "No pairing codes or channel not configured"
    done
    ;;
    
  approve)
    if [ -z "$2" ]; then
      echo "Usage: $0 approve <code> [channel]"
      echo ""
      echo "Example:"
      echo "  $0 approve ABC123"
      echo "  $0 approve ABC123 telegram"
      echo ""
      echo "Default channel: webchat"
      exit 1
    fi
    
    CODE="$2"
    CHANNEL="${3:-webchat}"
    
    echo "Approving pairing for $CHANNEL with code $CODE..."
    bun run openclaw pairing approve --channel "$CHANNEL" "$CODE"
    
    if [ $? -eq 0 ]; then
      echo ""
      echo "✓ Pairing approved successfully!"
      log "Pairing approved: $CHANNEL ($CODE)"
    else
      echo ""
      echo "ERROR: Failed to approve pairing"
      log "ERROR: Pairing approval failed for $CHANNEL" "error.log"
      exit 1
    fi
    ;;
    
  deny|reject)
    if [ -z "$2" ]; then
      echo "Usage: $0 deny <code> [channel]"
      echo ""
      echo "Example:"
      echo "  $0 deny ABC123"
      echo "  $0 deny ABC123 telegram"
      exit 1
    fi
    
    CODE="$2"
    CHANNEL="${3:-webchat}"
    
    echo "Denying pairing for $CHANNEL with code $CODE..."
    bun run openclaw pairing deny --channel "$CHANNEL" "$CODE"
    
    if [ $? -eq 0 ]; then
      echo ""
      echo "✓ Pairing denied"
      log "Pairing denied: $CHANNEL ($CODE)"
    else
      echo ""
      echo "ERROR: Failed to deny pairing"
      log "ERROR: Pairing denial failed for $CHANNEL" "error.log"
      exit 1
    fi
    ;;
    
  help|--help|-h)
    echo "=========================================="
    echo "OpenClaw Pairing Management"
    echo "=========================================="
    echo ""
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  list [channel]              List pending pairing codes for a channel"
    echo "                              (default: webchat)"
    echo "  list-all                    List codes for all channels"
    echo "  approve <code> [channel]    Approve a pairing request (default: webchat)"
    echo "  deny <code> [channel]       Deny a pairing request (default: webchat)"
    echo "  help                        Show this help message"
    echo ""
    echo "Channels: webchat, telegram, whatsapp, discord, signal, slack"
    echo ""
    echo "Examples:"
    echo "  $0 list"
    echo "  $0 list telegram"
    echo "  $0 list-all"
    echo "  $0 approve ABC123"
    echo "  $0 approve XYZ789 telegram"
    echo "  $0 deny ABC123 webchat"
    echo ""
    ;;
    
  *)
    echo "ERROR: Unknown command '$COMMAND'"
    echo ""
    echo "Run '$0 help' for usage information"
    exit 1
    ;;
esac

exit 0