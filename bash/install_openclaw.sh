#!/bin/bash

# Get Bash Variables
source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/env.sh"

echo "=========================================="
echo "OpenClaw AI Bot Installation"
echo "=========================================="
echo ""

OPENCLAW_DIR="$ROOT_DIR/openclaw"

log "Starting OpenClaw installation"

# Check if openclaw directory already exists
if [ -d "$OPENCLAW_DIR" ]; then
  read -p "OpenClaw directory exists. Reinstall? (y/n): " -n 1 -r
  echo
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -rf "$OPENCLAW_DIR"
    log "Removed existing OpenClaw directory for fresh install"
  else
    echo "Installation cancelled"
    exit 0
  fi
fi

# Clone fresh OpenClaw repository
echo "Cloning OpenClaw repository..."
git clone https://github.com/openclaw/openclaw.git "$OPENCLAW_DIR"

if [ $? -ne 0 ]; then
  echo "ERROR: Failed to clone OpenClaw repository"
  log "ERROR: Git clone failed" "error.log"
  exit 1
fi

# Navigate to openclaw directory
cd "$OPENCLAW_DIR" || exit 1

# Install required system packages
echo "Installing required system packages..."
require "curl"
require "unzip"
require "build-essential"
require "cmake"
require "pkg-config"
require "libssl-dev"

# Install Node.js 22+ if not present or version is too old
echo ""
echo "Checking Node.js version..."
if command -v node &> /dev/null; then
  NODE_MAJOR=$(node --version | cut -d'.' -f1 | sed 's/v//')
  if [ "$NODE_MAJOR" -lt 22 ]; then
    echo "Node.js version is too old ($NODE_MAJOR). Installing Node.js 22..."
    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
    sudo apt-get install -y nodejs
    log "Upgraded Node.js to version 22"
  else
    echo "✓ Node.js $(node --version) is installed"
  fi
else
  echo "Node.js not found. Installing Node.js 22..."
  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
  sudo apt-get install -y nodejs
  log "Installed Node.js 22"
fi

# Verify Node version
NODE_VERSION=$(node --version)
echo "Using Node.js $NODE_VERSION"

# Install Bun if not present
echo ""
echo "Checking for Bun installation..."

# Check if bun command is available
if command -v bun &> /dev/null; then
  echo "✓ Bun is already installed ($(bun --version))"
  export BUN_INSTALL="$HOME/.bun"
  export PATH="$BUN_INSTALL/bin:$PATH"
else
  echo "Installing Bun runtime..."
  
  # Install Bun
  curl -fsSL https://bun.sh/install | bash
  
  # Set Bun paths
  export BUN_INSTALL="$HOME/.bun"
  export PATH="$BUN_INSTALL/bin:$PATH"
  
  # Source bashrc to get Bun in PATH (the installer adds it)
  if [ -f "$HOME/.bashrc" ]; then
    # Extract just the Bun-related exports from bashrc
    if grep -q "BUN_INSTALL" "$HOME/.bashrc"; then
      export BUN_INSTALL="$HOME/.bun"
      export PATH="$BUN_INSTALL/bin:$PATH"
    fi
  fi
  
  # Verify Bun was installed successfully
  if [ -f "$BUN_INSTALL/bin/bun" ]; then
    echo "✓ Bun installed successfully"
    
    # Test if it's executable
    if "$BUN_INSTALL/bin/bun" --version &> /dev/null; then
      echo "✓ Bun is working: $("$BUN_INSTALL/bin/bun" --version)"
      log "Installed Bun runtime: $("$BUN_INSTALL/bin/bun" --version)"
    else
      echo "ERROR: Bun binary exists but is not executable"
      log "ERROR: Bun not executable" "error.log"
      exit 1
    fi
  else
    echo "ERROR: Bun installation failed"
    echo "Expected location: $BUN_INSTALL/bin/bun"
    echo ""
    echo "Attempting manual installation..."
    
    # Try manual installation
    mkdir -p "$HOME/.bun/bin"
    LATEST_BUN=$(curl -fsSL https://api.github.com/repos/oven-sh/bun/releases/latest | grep "tag_name" | cut -d'"' -f4)
    
    if [ -z "$LATEST_BUN" ]; then
      LATEST_BUN="v1.1.34"
    fi
    
    echo "Downloading Bun $LATEST_BUN..."
    curl -fsSL "https://github.com/oven-sh/bun/releases/download/${LATEST_BUN}/bun-linux-x64.zip" -o /tmp/bun.zip
    
    unzip -q /tmp/bun.zip -d /tmp/
    mv /tmp/bun-linux-x64/bun "$HOME/.bun/bin/"
    chmod +x "$HOME/.bun/bin/bun"
    rm -rf /tmp/bun.zip /tmp/bun-linux-x64
    
    if [ -f "$HOME/.bun/bin/bun" ]; then
      echo "✓ Manual Bun installation successful"
      log "Installed Bun manually"
    else
      echo "ERROR: Failed to install Bun"
      log "ERROR: Bun installation failed completely" "error.log"
      exit 1
    fi
  fi
fi

# Final verification that Bun is accessible
if ! command -v bun &> /dev/null; then
  echo ""
  echo "WARNING: Bun is installed but not in current PATH"
  echo "Location: $BUN_INSTALL/bin/bun"
  echo ""
  echo "Please run the following commands:"
  echo "  source ~/.bashrc"
  echo "  ./bash/run_openclaw.sh"
  echo ""
  log "Bun installed but not in PATH" "error.log"
  exit 1
fi

echo "✓ Using Bun $(bun --version)"

# Clean node_modules if reinstalling
if [ -d "node_modules" ]; then
  echo ""
  echo "Cleaning old node_modules..."
  rm -rf node_modules
fi

# Install OpenClaw dependencies using Bun
echo ""
echo "Installing OpenClaw dependencies with Bun (this may take several minutes)..."
echo "Note: Building node-llama-cpp requires CMake and may take a while..."
bun install

if [ $? -ne 0 ]; then
  echo "ERROR: Failed to install dependencies"
  log "ERROR: bun install failed" "error.log"
  exit 1
fi

log "Dependencies installed successfully with Bun"

# Build UI components
echo ""
echo "Building UI components..."
bun run ui:build

if [ $? -ne 0 ]; then
  echo "WARNING: UI build had issues, but continuing..."
  log "WARNING: UI build had issues" "error.log"
fi

log "UI build completed"

# Build the project
echo ""
echo "Building OpenClaw..."
bun run build

if [ $? -eq 0 ]; then
  echo "✓ Build completed successfully"
  log "OpenClaw build completed successfully"
else
  echo "ERROR: Build failed"
  log "ERROR: OpenClaw build failed" "error.log"
  exit 1
fi

# Check for .env file
echo ""
echo "=========================================="
echo "Configuration Setup"
echo "=========================================="
echo ""

if [ ! -f ".env" ]; then
  echo "Creating .env file from template..."
  cp .env.example .env
  log "Created .env file from template"
  echo "✓ .env file created"
else
  echo "✓ .env file already exists"
fi

echo ""
echo "Your .env file is at: $OPENCLAW_DIR/.env"
echo ""
echo "IMPORTANT: You need to configure your AI model credentials"
echo "OpenClaw supports:"
echo "  - Claude (Anthropic) - Recommended"
echo "  - ChatGPT (OpenAI)"
echo ""
echo "Edit the .env file to add your API keys or session tokens."
echo ""

echo "=========================================="
echo "Installation Complete!"
echo "=========================================="
echo ""
echo "Installation directory: $OPENCLAW_DIR"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your AI credentials:"
echo "   nano $OPENCLAW_DIR/.env"
echo ""
echo "2. Run the bot initialization:"
echo "   ./bash/run_openclaw.sh"
echo ""
echo "Documentation: https://docs.openclaw.ai"
echo ""

# Fix ownership of openclaw directory
sudo chown -R ubuntu:ubuntu /local/openclaw
# Make it writable
chmod -R u+w /local/openclaw
# Allow OpenClaw Gateway port
sudo ufw allow 18789/tcp comment 'OpenClaw Gateway'
# Allow Bridge port if needed
#sudo ufw allow 18790/tcp comment 'OpenClaw Bridge'
# Reload firewall
sudo ufw reload
# Check status
sudo ufw status

log "OpenClaw installation completed successfully"

exit 0