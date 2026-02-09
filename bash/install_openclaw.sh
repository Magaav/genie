# 1. Firewall
sudo ufw allow 18789/tcp comment 'OpenClaw Gateway'

# 2. Clone and prepare (no sudo needed for git/mkdir)
git clone https://github.com/openclaw/openclaw.git /local/openclaw
cd /local/openclaw
mkdir -p /local/.openclaw/workspace
sudo chown -R 1000:1000 /local/.openclaw

# 3. Setup variables (Ensure they point to YOUR home)
export OPENCLAW_CONFIG_DIR="/local/.openclaw"
export OPENCLAW_WORKSPACE_DIR="/local/.openclaw/workspace"
export OPENCLAW_GATEWAY_BIND=lan
export OPENCLAW_GATEWAY_TOKEN=$(openssl rand -hex 32)

# 4. Run setup (Crucial: do NOT use sudo here)
# This keeps the files in your home folder from the start
./docker-setup.sh

# 5. Fix ownership once to match the Docker 'node' user when using Oracle Public Cloud
sudo chown -R 1000:1000 /local/.openclaw
sudo chmod -R 777 /local/.openclaw
sudo usermod -aG opc ubuntu
newgrp opc

# 6. Alias
echo "alias openclaw='docker compose -f /local/openclaw/docker-compose.yml exec openclaw-gateway node dist/index.js'" >> ~/.bashrc
source ~/.bashrc