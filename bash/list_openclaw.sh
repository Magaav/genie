# Connect local computer to openclaw server
ssh -N -L 19789:127.0.0.1:18789 openclaw.ohana

# Use in /local/openclaw folder
docker compose up -d openclaw-gateway
sudo docker compose restart openclaw-gateway
sudo docker compose exec openclaw-gateway node dist/index.js configure --section model
sudo docker compose exec openclaw-gateway node dist/index.js devices list
sudo docker compose exec openclaw-gateway node dist/index.js devices approve $DEVICE_ID
docker compose exec openclaw-gateway ls -la /home/node/.openclaw_backup/