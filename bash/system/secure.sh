#!/bin/bash

# Get Bash Variables
source "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/env.sh"
# Check required packages
require "fail2ban"

# Basic critical Security and Initial setup script for Ubuntu 24 Oracle instance
# Run this script as root or with sudo

echo "Starting security setup..."

# 1. Configure SSH for key-based authentication only and disable root login
echo "Configuring SSH for key-based auth and disabling root login..."
sudo sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config
sudo systemctl restart ssh

# 2. Install and configure UFW to allow only SSH
echo "Installing and configuring UFW..."
sudo apt install ufw -y
sudo ufw allow ssh
sudo ufw --force enable

# 3. Install Fail2ban for SSH protection
# Check if fail2ban is already running
if systemctl is-active --quiet fail2ban; then
  echo "Fail2ban is already running. Skipping server_start."
else
  sudo systemctl start fail2ban
  sudo systemctl enable fail2ban
  # sudo service fail2ban start
  sudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local
  # Enable default jails
  sudo tee /etc/fail2ban/jail.local > /dev/null <<EOF
[INCLUDES]
before = paths-debian.conf

[DEFAULT]
ignorecommand =
bantime  = 10m
findtime  = 10m
maxretry = 5
maxmatches = %(maxretry)s
backend = auto
usedns = warn
logencoding = auto
enabled = false
mode = normal
filter = %(__name__)s[mode=%(mode)s]
destemail = root@localhost
sender = root@<fq-hostname>
mta = sendmail
protocol = tcp
chain = <known/chain>
port = 0:65535
fail2ban_agent = Fail2Ban/%(fail2ban_version)s
banaction = iptables-multiport
banaction_allports = iptables-allports
action_ = %(banaction)s[port="%(port)s", protocol="%(protocol)s", chain="%(chain)s"]
action_mw = %(action_)s
            %(mta)s-whois[sender="%(sender)s", dest="%(destemail)s", protocol="%(protocol)s", chain="%(chain)s"]
action_mwl = %(action_)s
             %(mta)s-whois-lines[sender="%(sender)s", dest="%(destemail)s", logpath="%(logpath)s", chain="%(chain)s"]
action_xarf = %(action_)s
             xarf-login-attack[service=%(__name__)s, sender="%(sender)s", logpath="%(logpath)s", port="%(port)s"]
action_cf_mwl = cloudflare[cfuser="%(cfemail)s", cftoken="%(cfapikey)s"]
                %(mta)s-whois-lines[sender="%(sender)s", dest="%(destemail)s", logpath="%(logpath)s", chain="%(chain)s"]
action_blocklist_de  = blocklist_de[email="%(sender)s", service="%(__name__)s", apikey="%(blocklist_de_apikey)s", agent="%(fail2ban_agent)s"]
action_badips = badips.py[category="%(__name__)s", banaction="%(banaction)s", agent="%(fail2ban_agent)s"]
action_badips_report = badips[category="%(__name__)s", agent="%(fail2ban_agent)s"]
action_abuseipdb = abuseipdb
action = %(action_)s

[sshd]
port    = ssh
logpath = %(sshd_log)s
backend = %(sshd_backend)s
enable = true
maxretry = 5
EOF

  sudo systemctl restart fail2ban
  echo "####### Fail2ban is now running #######"
  sudo fail2ban-client status sshd
  echo "#######  #######"
  log "Fail2ban restarted to apply configuration"
fi
# Fail2ban defaults to monitoring SSH; ensure it's active
sudo systemctl enable fail2ban
sudo systemctl start fail2ban

echo "Security setup complete. Rebooting for full effect..."
sudo reboot