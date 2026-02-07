#!/bin/bash

# Get Bash Variables
source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/env.sh"

echo "=========================================="
echo "OpenClaw Bot Initialization"
echo "=========================================="
echo ""

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
  echo ""
  echo "Searched locations:"
  echo "  - $HOME/.bun/bin/bun"
  if [ -n "$SUDO_USER" ]; then
    echo "  - $ACTUAL_USER_HOME/.bun/bin/bun"
  fi
  echo ""
  echo "Please run ./bash/install_openclaw.sh first to install Bun"
  echo ""
  echo "If you just installed Bun, try:"
  echo "  source ~/.bashrc"
  echo "  ./bash/run_openclaw.sh"
  echo ""
  echo "Or check installation with:"
  echo "  ls -la ~/.bun/bin/"
  exit 1
fi

echo "✓ Using Bun $(bun --version)"

# Add Bun to .bashrc if not already there
if ! grep -q 'BUN_INSTALL.*\.bun' ~/.bashrc; then
  echo "Adding Bun to ~/.bashrc for permanent PATH access..."
  echo '' >> ~/.bashrc
  echo '# Bun runtime' >> ~/.bashrc
  echo 'export BUN_INSTALL="$HOME/.bun"' >> ~/.bashrc
  echo 'export PATH="$BUN_INSTALL/bin:$PATH"' >> ~/.bashrc
  echo "✓ Bun added to ~/.bashrc"
  log "Added Bun to ~/.bashrc"
  echo ""
fi

OPENCLAW_DIR="$ROOT_DIR/openclaw"

# Check if openclaw directory exists
if [ ! -d "$OPENCLAW_DIR" ]; then
  echo "ERROR: OpenClaw not found at $OPENCLAW_DIR"
  echo "Please run ./bash/install_openclaw.sh first"
  exit 1
fi

cd "$OPENCLAW_DIR" || exit 1

log "Initializing OpenClaw bot instance"

# Check if dependencies are installed
if [ ! -d "node_modules" ]; then
  echo "ERROR: Dependencies not installed"
  echo "Please run ./bash/install_openclaw.sh first"
  exit 1
fi

# Check if build exists
if [ ! -d "dist" ]; then
  echo "ERROR: Project not built"
  echo "Please run ./bash/install_openclaw.sh first"
  exit 1
fi

# Verify .env file exists
if [ ! -f ".env" ]; then
  echo "WARNING: No .env file found!"
  echo "Creating .env from template..."
  if [ -f ".env.example" ]; then
    cp .env.example .env
    echo "✓ .env file created"
  fi
  echo "Please configure your .env file with API keys before continuing"
  read -p "Press Enter after configuring .env to continue..."
fi

echo "=========================================="
echo "Running OpenClaw Onboarding"
echo "=========================================="
echo ""
echo "The onboarding wizard will help you:"
echo "  1. Configure your AI model authentication"
echo "  2. Set up messaging channels (WhatsApp, Telegram, etc.)"
echo "  3. Install the gateway daemon (optional)"
echo "  4. Configure initial skills"
echo ""

read -p "Do you want to run the onboarding wizard? (y/n): " -n 1 -r
echo
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
  echo "Starting onboarding wizard..."
  log "Running OpenClaw onboarding wizard"
  bun run openclaw onboard
  
  if [ $? -eq 0 ]; then
    echo "✓ Onboarding completed successfully"
    log "OpenClaw onboarding completed successfully"
  else
    echo "WARNING: Onboarding had some issues"
    log "OpenClaw onboarding had issues" "error.log"
  fi
else
  echo "Skipping onboarding wizard"
  log "Skipped OpenClaw onboarding wizard"
fi

echo ""
echo "=========================================="
echo "OpenClaw Bot Ready!"
echo "=========================================="
echo ""
echo "Quick start commands (run from $OPENCLAW_DIR):"
echo ""
echo "1. Start the Gateway (control plane):"
echo "   cd $OPENCLAW_DIR"
echo "   bun run openclaw gateway --port 18789 --verbose"
echo ""
echo "2. Or start in development mode with auto-reload:"
echo "   cd $OPENCLAW_DIR"
echo "   bun run gateway:watch"
echo ""
echo "3. Talk to the assistant:"
echo "   bun run openclaw agent --message \"Hello, how can you help me?\""
echo ""
echo "4. Send a message to a channel:"
echo "   bun run openclaw message send --to +1234567890 --message \"Hello\""
echo ""
echo "5. Check system health:"
echo "   bun run openclaw doctor"
echo ""
echo "6. View all available commands:"
echo "   bun run openclaw --help"
echo ""
echo "Alternative: Run with Docker Compose:"
echo "   cd $OPENCLAW_DIR"
echo "   docker-compose up -d"
echo ""
echo "Documentation: https://docs.openclaw.ai"
echo "Getting Started: https://docs.openclaw.ai/start/getting-started"
echo ""

log "OpenClaw bot initialization completed"

exit 0