#!/bin/bash

# Get Bash Variables
source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/env.sh"

echo "Starting repository sync..."

# Check if /local is a git repository
if [ ! -d "$ROOT_DIR/.git" ]; then
  echo "ERROR: $ROOT_DIR is not a git repository"
  echo "Please clone your repository first using:"
  echo "git clone git@github.com-openclaw:YOUR_USERNAME/openclaw.git /local"
  log "ERROR: Sync failed - not a git repository" "error.log"
  exit 1
fi

# Navigate to repository
cd "$ROOT_DIR" || exit 1

# Check if we have SSH access
echo "Testing GitHub SSH connection..."
ssh -T git@github.com-openclaw 2>&1 | grep -q "successfully authenticated"
if [ $? -ne 0 ]; then
  echo "WARNING: GitHub SSH authentication may not be configured correctly"
  echo "Please ensure you've added the SSH key to your GitHub repository"
  log "WARNING: GitHub SSH authentication test failed" "error.log"
fi

# Fetch latest changes
echo "Fetching latest changes from remote..."
git fetch origin
log "Git fetch completed"

# Get current branch
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "Current branch: $CURRENT_BRANCH"

# Pull latest changes
echo "Pulling latest changes..."
git pull origin "$CURRENT_BRANCH"

if [ $? -eq 0 ]; then
  echo "Repository synced successfully!"
  log "Repository synced successfully on branch $CURRENT_BRANCH"
else
  echo "ERROR: Failed to sync repository"
  log "ERROR: Git pull failed" "error.log"
  exit 1
fi

echo ""
echo "Sync complete! Your /local directory is now up to date."
echo ""
echo "To commit and push changes:"
echo "  git ac \"your commit message\""
echo "  git push"