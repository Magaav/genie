# Restart the service to pick up new config
systemctl --user restart openclaw-gateway.service

# Check status
systemctl --user status openclaw-gateway.service

# View logs
journalctl --user -u openclaw-gateway.service -f