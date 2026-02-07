#!/bin/bash

# Get Bash Variables
source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/env.sh"

echo "=========================================="
echo "Configuring OpenClaw for Nginx Proxy"
echo "=========================================="
echo ""

OPENCLAW_DIR="$ROOT_DIR/openclaw"
CONFIG_FILE="$OPENCLAW_DIR/.config.json5"

cd "$OPENCLAW_DIR" || exit 1

# Backup existing config if it exists
if [ -f "$CONFIG_FILE" ]; then
    echo "Backing up existing config..."
    cp "$CONFIG_FILE" "$CONFIG_FILE.backup.$(date +%Y%m%d_%H%M%S)"
    echo "✓ Backup created"
    log "Backed up existing OpenClaw config"
fi

echo "Creating OpenClaw configuration with nginx proxy support..."

cat > "$CONFIG_FILE" <<'EOF'
{
  gateway: {
    trustedProxies: ["127.0.0.1"],
    bind: "loopback",
    port: 18789,
  }
}
EOF

echo "✓ OpenClaw configuration created at: $CONFIG_FILE"
log "Created OpenClaw config with trustedProxies for nginx"

# Restart gateway
echo ""
echo "Restarting OpenClaw gateway to apply configuration..."

if pgrep -f "openclaw gateway" > /dev/null; then
    echo "Stopping current gateway..."
    sudo pkill -f "openclaw gateway"
    sleep 3
    log "Stopped OpenClaw gateway for reconfiguration"
fi

echo "Starting gateway with new configuration..."
sudo bash "$ROOT_DIR/bash/start_gateway.sh"

echo ""
echo "=========================================="
echo "Configuration Complete!"
echo "=========================================="
echo ""
echo "The gateway now trusts nginx proxy connections."
echo ""
echo "Get your dashboard URL with:"
echo "  sudo bash /local/bash/dashboard.sh"
echo ""

log "OpenClaw proxy configuration completed"

exit 0