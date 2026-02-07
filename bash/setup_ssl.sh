#!/bin/bash

# Get Bash Variables
source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/system/env.sh"

DOMAIN="zangao.colmeio.com"
EMAIL="vic.scar@gmail.com"

echo "=========================================="
echo "Setting up SSL for OpenClaw"
echo "=========================================="
echo "Domain: $DOMAIN"
echo "Email: $EMAIL"
echo ""

# Install nginx and certbot
echo "Installing nginx and certbot..."
require "nginx"
require "certbot"
require "python3-certbot-nginx"

# Stop nginx temporarily
sudo systemctl stop nginx

# Configure nginx for OpenClaw (HTTP only first, certbot will add HTTPS)
echo "Configuring nginx..."
sudo tee /etc/nginx/sites-available/openclaw > /dev/null <<EOF
server {
    listen 80;
    server_name $DOMAIN;
    
    # WebSocket upgrade headers
    location / {
        proxy_pass http://127.0.0.1:18789;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # WebSocket timeouts
        proxy_connect_timeout 7d;
        proxy_send_timeout 7d;
        proxy_read_timeout 7d;
    }
}
EOF

# Enable the site
sudo ln -sf /etc/nginx/sites-available/openclaw /etc/nginx/sites-enabled/openclaw
sudo rm -f /etc/nginx/sites-enabled/default

# Test nginx config
echo "Testing nginx configuration..."
sudo nginx -t

if [ $? -ne 0 ]; then
    echo "ERROR: Nginx configuration test failed"
    exit 1
fi

# Start nginx
sudo systemctl start nginx
sudo systemctl enable nginx

# Open ports for HTTP and HTTPS
echo "Opening ports 80 and 443..."
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw status

# Get SSL certificate
echo ""
echo "Obtaining SSL certificate from Let's Encrypt..."
echo "Certbot will automatically modify the nginx config to add HTTPS..."
echo ""

sudo certbot --nginx -d $DOMAIN --email $EMAIL --agree-tos --non-interactive --redirect

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "SSL Setup Complete!"
    echo "=========================================="
    echo ""
    echo "Your OpenClaw gateway is now available at:"
    echo "https://$DOMAIN/"
    echo ""
    echo "With token:"
    echo "https://$DOMAIN/#token=86b77b0cd17da89eafe575a63f2c3af2c7cc9e367b79668a"
    echo ""
    echo "SSL certificate will auto-renew via certbot timer"
    echo ""
    log "SSL setup completed for $DOMAIN"
else
    echo ""
    echo "ERROR: Failed to obtain SSL certificate"
    echo "Make sure:"
    echo "  1. DNS is propagated (try: ping $DOMAIN)"
    echo "  2. Ports 80 and 443 are open in Oracle Cloud Security List"
    echo ""
    log "ERROR: SSL certificate request failed" "error.log"
    exit 1
fi

exit 0