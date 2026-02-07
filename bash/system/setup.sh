#!/bin/bash

# Get Bash Variables
source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/env.sh"

echo "Starting setup process..."

# Set the timezone to America/Sao_Paulo
echo "Setting timezone to America/Sao_Paulo..."
sudo timedatectl set-timezone America/Sao_Paulo
log "Timezone set to America/Sao_Paulo"

# Install Docker
# Install Docker
set_docker(){
  echo "Installing Docker..."
  # Remove old versions if they exist
  sudo apt-get remove -y docker docker-engine docker.io containerd runc || true
  # Update package index
  sudo apt-get update
  # Install prerequisites
  sudo apt-get install -y apt-transport-https ca-certificates curl software-properties-common gnupg lsb-release
  # Add Docker's official GPG key (using apt-key method for compatibility)
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
  # Add the Docker repository to APT sources
  sudo add-apt-repository -y "deb [arch=$(dpkg --print-architecture)] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
  # Update the package database with the Docker packages from the newly added repo
  sudo apt-get update
  # Verify we're installing from Docker repo (optional check)
  echo "Checking Docker repository..."
  sudo apt-cache policy docker-ce
  # Install Docker Engine
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  # Start and enable Docker
  sudo systemctl start docker
  sudo systemctl enable docker
  # Determine the actual user
  if [ -n "$SUDO_USER" ]; then
    ACTUAL_USER="$SUDO_USER"
  else
    ACTUAL_USER="$USER"
  fi
  # Add user to docker group
  sudo usermod -aG docker $ACTUAL_USER
  echo "Added $ACTUAL_USER to docker group"
  log "Added $ACTUAL_USER to docker group"
  # Change docker.sock permissions to ensure immediate access
  sudo chown root:docker /var/run/docker.sock
  sudo chmod 666 /var/run/docker.sock
  # Restart Docker service to apply changes
  sudo systemctl restart docker
  # Install Docker Compose standalone (in addition to plugin)
  DOCKER_COMPOSE_VERSION="v2.24.5"
  echo "Installing Docker Compose standalone..."
  sudo curl -L "https://github.com/docker/compose/releases/download/${DOCKER_COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
  sudo chmod +x /usr/local/bin/docker-compose
  # Create symbolic link if needed
  sudo ln -sf /usr/local/bin/docker-compose /usr/bin/docker-compose
  # Verify Docker Compose installation
  if command -v docker-compose >/dev/null 2>&1; then
    echo "Docker Compose version: $(docker-compose --version)"
    log "Docker Compose installed: $(docker-compose --version)"
  fi
  # Apply group changes for current session (for the actual user)
  if [ -n "$SUDO_USER" ]; then
    echo ""
    echo "=========================================="
    echo "⚠️  IMPORTANT - Group Changes Applied"
    echo "=========================================="
    echo ""
    echo "The user '$ACTUAL_USER' has been added to the docker group."
    echo ""
    echo "For VS Code Remote SSH, you need to:"
    echo "1. Close VS Code completely"
    echo "2. Reconnect to the remote server"
    echo ""
    echo "OR run this command in a NEW terminal:"
    echo "  newgrp docker"
    echo ""
    echo "Current session group changes will not take effect until reconnection."
    echo "=========================================="
    echo ""
  fi
  # Verify Docker installation with current permissions
  echo "Verifying Docker installation..."
  if sudo docker run --rm hello-world >/dev/null 2>&1; then
    echo "✓ Docker installed successfully!"
    log "Docker installation completed successfully"
  else
    echo "⚠ Docker installed but verification failed"
    log "Docker installed with warnings" "error.log"
  fi
  # Test if current user can run docker (might fail before reconnect)
  if docker ps >/dev/null 2>&1; then
    echo "✓ Docker accessible without sudo"
  else
    echo "⚠ Docker requires reconnection to work without sudo"
    echo "  Socket permissions set to 666 for immediate access"
  fi
  echo ""
  echo "Docker installation complete!"
}

# Install Github and connects to our repositories via ssh keys
# Install Github and connects to our repositories via ssh keys
set_github(){
  echo "Setting up GitHub SSH access..."
  # Validate required environment variables
  if [ -z "$INSTANCE_NAME" ] || [ -z "$INSTANCE_EMAIL" ]; then
    echo "ERROR: INSTANCE_NAME or INSTANCE_EMAIL not set in env.sh"
    log "ERROR: GitHub setup failed - missing INSTANCE_NAME or INSTANCE_EMAIL" "error.log"
    exit 1
  fi
  # Install required packages
  require "git"
  # Configure Git global settings
  echo "Configuring Git with instance credentials..."
  git config --global user.name "$INSTANCE_NAME"
  git config --global user.email "$INSTANCE_EMAIL"
  git config --global alias.ac '!git add . && git commit -m'
  # Add Git alias for quick commits
  log "Git configured with name: $INSTANCE_NAME and email: $INSTANCE_EMAIL"
  echo "Git configured successfully!"
  echo "  - User Name: $INSTANCE_NAME"
  echo "  - User Email: $INSTANCE_EMAIL"
  echo "  - Alias 'ac' added: Use 'git ac \"commit message\"' to add all and commit"
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
    log "SSH key already exists, skipping generation"
  else
    echo "Generating SSH key for GitHub..."
    ssh-keygen -t ed25519 -C "$INSTANCE_EMAIL" -f "$SSH_KEY_PATH" -N ""
    log "SSH key generated at $SSH_KEY_PATH"
  fi
  # Set proper ownership for the SSH files
  if [ -n "$SUDO_USER" ]; then
    chown -R "$ACTUAL_USER:$ACTUAL_USER" "$SSH_DIR"
  fi
  # Start ssh-agent and add the key
  eval "$(ssh-agent -s)"
  ssh-add "$SSH_KEY_PATH"
  log "SSH key added to ssh-agent"
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
    log "SSH config updated for GitHub"
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
  echo "  git add ."
  echo "  git commit -m 'Initial commit'"
  echo "  git remote add origin git@github.com:Magaav/openclaw.git"
  echo "  git push -u origin master"
  echo ""
  echo "SSH key location: $SSH_KEY_PATH"
  echo "SSH key owner: $ACTUAL_USER"
  echo ""
  
  log "GitHub setup completed - SSH key ready at $SSH_KEY_PATH"
}

# Run setup functions
set_docker
set_github

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo "Next: Configure the SSH key in GitHub, then run 'sudo ./bash/server.sh sync' to sync your repository"