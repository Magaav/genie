cat > ~/.openclaw/openclaw.json <<'EOF'
{
  "gateway": {
    "mode": "local",
    "trustedProxies": ["127.0.0.1", "::1", "200.233.207.4"],
    "bind": "loopback",
    "port": 18789,
    "auth": {
      "token": "86b77b0cd17da89eafe575a63f2c3af2c7cc9e367b79668a"
    },
    "controlUi": {
      "allowedOrigins": ["https://zangao.colmeio.com"]
    }
  }
}
EOF

cp ~/.openclaw/openclaw.json /local/openclaw/openclaw.json

pkill -f "openclaw gateway"
systemctl --user stop openclaw-gateway.service 2>/dev/null
sleep 2

cd /local/openclaw
openclaw gateway --verbose