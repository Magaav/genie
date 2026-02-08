#!/bin/bash

# Get Bash Variables
source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/env.sh"

# Validate required environment variables
if [ -z "$INSTANCE_NAME" ] || [ -z "$INSTANCE_EMAIL" ]; then
  echo "ERROR: INSTANCE_NAME or INSTANCE_EMAIL not set in env.sh"
  exit 1
fi

set_git(){
  # Install required packages
  require "git"
  # Determine the actual user and home directory
  if [ -n "$SUDO_USER" ]; then
    ACTUAL_USER="$SUDO_USER"
    ACTUAL_HOME=$(getent passwd "$SUDO_USER" | cut -d: -f6)
  else
    ACTUAL_USER="$USER"
    ACTUAL_HOME="$HOME"
  fi
  # Generate SSH key for GitHub
  SSH_DIR="$ACTUAL_HOME/.ssh"
  SSH_KEY_PATH="$SSH_DIR/id_ed25519"
  # Create .ssh directory if it doesn't exist
  mkdir -p "$SSH_DIR"
  chmod 700 "$SSH_DIR"
  if [ -f "$SSH_KEY_PATH" ]; then
    echo "SSH key already exists at $SSH_KEY_PATH"
    echo "SSH key already exists, skipping generation"
  else
    echo "Generating SSH key for GitHub..."
    ssh-keygen -t ed25519 -C "$INSTANCE_EMAIL" -f "$SSH_KEY_PATH" -N ""
    echo "SSH key generated at $SSH_KEY_PATH"
  fi
  # Set proper ownership for the SSH files
  if [ -n "$SUDO_USER" ]; then
    chown -R "$ACTUAL_USER:$ACTUAL_USER" "$SSH_DIR"
  fi
  # Start ssh-agent and add the key
  eval "$(ssh-agent -s)"
  ssh-add "$SSH_KEY_PATH"
  echo "SSH key added to ssh-agent"
  # Configure SSH to use this key for GitHub
  SSH_CONFIG="$SSH_DIR/config"
  if ! grep -q "Host github.com" "$SSH_CONFIG" 2>/dev/null; then
    cat >> "$SSH_CONFIG" << 'EOF'
# GitHub configuration
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes
EOF
    chmod 600 "$SSH_CONFIG"
    if [ -n "$SUDO_USER" ]; then
      chown "$ACTUAL_USER:$ACTUAL_USER" "$SSH_CONFIG"
    fi
    echo "SSH config updated for GitHub"
  fi
  # Display the public key and copy to clipboard
  echo ""
  echo "=========================================="
  echo "GitHub SSH Key Setup Complete!"
  echo "=========================================="
  echo ""
  # Use VS Code's clipboard integration if available
  if command -v code >/dev/null 2>&1 && [ -n "$VSCODE_IPC_HOOK_CLI" ]; then
    # VS Code Remote is active - use clipboard integration
    cat "$SSH_KEY_PATH.pub" | code --stdin --wait 2>/dev/null && \
      echo "✓ SSH key opened in VS Code editor" || true
    # Also try direct clipboard copy via VS Code
    if cat "$SSH_KEY_PATH.pub" | xclip -selection clipboard 2>/dev/null; then
      echo "✓ SSH public key copied to clipboard via xclip"
    else
      # Fallback: display for manual copy
      echo "📋 SELECT AND COPY THIS SSH KEY (Ctrl+Shift+C in terminal):"
      echo ""
      echo "=========================================="
      cat "$SSH_KEY_PATH.pub"
      echo "=========================================="
    fi
  else
    # No VS Code - just display the key
    echo "📋 SSH PUBLIC KEY - Copy this to GitHub:"
    echo "=========================================="
    cat "$SSH_KEY_PATH.pub"
    echo "=========================================="
  fi
  echo ""
  echo "NEXT STEPS:"
  echo "1. Copy the SSH key above (if not already copied)"
  echo "2. Go to: https://github.com/settings/ssh/new"
  echo "3. Title: '$INSTANCE_NAME'"
  echo "4. Paste the key and click 'Add SSH key'"
  echo ""
  echo "Then initialize and push your repository with:"
  echo "  cd /local"
  echo "  git init"
  echo "  git config --global --add safe.directory /local"
  echo "  git remote add origin git@github.com:Magaav/openclaw.git"
  echo "  git fetch origin"
  echo "  git clean -fd"
  echo "  git pull origin master"
  echo ""
  echo "SSH key location: $SSH_KEY_PATH"
  echo "SSH key owner: $ACTUAL_USER"
  echo ""
  
  log "GitHub setup completed - SSH key ready at $SSH_KEY_PATH"
}

config_git(){
  # Configure Git global settings
  echo "Should be run without sudo to set config for the actual user"
  echo "Configuring Git with instance credentials..."
  git config --global user.name "$INSTANCE_NAME"
  git config --global user.email "$INSTANCE_EMAIL"
  git config --global alias.ac '!git add . && git commit -m && git push --set-upstream origin master'
  echo "Git configured with name: $INSTANCE_NAME and email: $INSTANCE_EMAIL"
}

# Main script logic to call functions based on the input argument
case "$1" in
  set) set_git ;;
  config) config_git ;;
  *)
    echo "Usage: $0 {set|config}"
    exit 1
  ;;
esac