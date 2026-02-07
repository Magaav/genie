#!/bin/bash

# Get Bash Variables
source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/env.sh"

OPENCLAW_DIR="$ROOT_DIR/openclaw"

# Try to find Bun
if [ -f "$HOME/.bun/bin/bun" ]; then
  export BUN_INSTALL="$HOME/.bun"
  export PATH="$BUN_INSTALL/bin:$PATH"
elif [ -f "/root/.bun/bin/bun" ]; then
  export BUN_INSTALL="/root/.bun"
  export PATH="$BUN_INSTALL/bin:$PATH"
fi

cd "$OPENCLAW_DIR" || exit 1

# Show dashboard URL
bun run openclaw dashboard