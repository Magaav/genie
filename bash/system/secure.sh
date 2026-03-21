#!/bin/bash

# Get Bash Variables
source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/env.sh"

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  echo "Run this script as root: sudo bash $0"
  exit 1
fi

# Check required packages
require "fail2ban"
require "ufw"

# Basic critical Security and Initial setup script for Ubuntu 24 Oracle instance
# Run this script as root

echo "Starting security setup..."

set_sshd_option() {
  local key="$1"
  local value="$2"
  local config_file="/etc/ssh/sshd_config"

  if grep -qE "^[#[:space:]]*${key}[[:space:]]+" "$config_file"; then
    sed -i "s|^[#[:space:]]*${key}[[:space:]].*|${key} ${value}|" "$config_file"
  else
    printf '\n%s %s\n' "$key" "$value" >> "$config_file"
  fi
}

restart_ssh_service() {
  if systemctl list-unit-files | grep -q '^ssh\.service'; then
    systemctl restart ssh
  else
    systemctl restart sshd
  fi
}

wait_for_fail2ban() {
  local attempts=10
  local delay_seconds=1
  local attempt

  for ((attempt=1; attempt<=attempts; attempt++)); do
    if systemctl is-active --quiet fail2ban && fail2ban-client ping >/dev/null 2>&1; then
      return 0
    fi
    sleep "$delay_seconds"
  done

  return 1
}

# 1. Configure SSH for key-based authentication only and disable root login
echo "Configuring SSH for key-based auth and disabling root login..."
cp /etc/ssh/sshd_config "/etc/ssh/sshd_config.bak.${NOW}"
set_sshd_option "PasswordAuthentication" "no"
set_sshd_option "PermitRootLogin" "no"
sshd -t
restart_ssh_service

# 2. Install and configure UFW to allow only SSH
echo "Installing and configuring UFW..."
ufw allow OpenSSH
ufw --force enable

# 3. Disable rpcbind when NFS is not used
echo "Disabling rpcbind because NFS is not in use..."
systemctl disable --now rpcbind rpcbind.socket

# 4. Install Fail2ban for SSH protection
mkdir -p /etc/fail2ban/jail.d
cat > /etc/fail2ban/jail.d/sshd.local <<EOF
[DEFAULT]
bantime = 10m
findtime = 10m
maxretry = 5

[sshd]
enabled = true
port = ssh
backend = %(sshd_backend)s
logpath = %(sshd_log)s
EOF

# Fail2ban defaults to monitoring SSH; ensure it's active
systemctl enable fail2ban
systemctl restart fail2ban

if wait_for_fail2ban; then
  echo "####### Fail2ban is now running #######"
  fail2ban-client status sshd || true
  echo "#######  #######"
  log "Fail2ban restarted to apply configuration"
else
  echo "Fail2ban did not become ready in time."
  systemctl status fail2ban --no-pager -l || true
  journalctl -u fail2ban -n 50 --no-pager || true
  exit 1
fi

echo "Security setup complete."
echo "SSH config backup: /etc/ssh/sshd_config.bak.${NOW}"
echo "No reboot was forced. Reboot manually if you want a clean post-hardening restart."
