#!/usr/bin/env bash
# install.sh — Install ppdmwatch as a systemd service on Linux
set -euo pipefail

INSTALL_DIR="/opt/ppdmwatch"
LOG_DIR="/var/log/ppdmwatch"
SVC_USER="ppdmwatch"

echo "=== Installing PPDM Watch Agent ==="

# Create dedicated service user
sudo useradd -r -s /bin/false "$SVC_USER" 2>/dev/null || true

# Create directories
sudo mkdir -p "$INSTALL_DIR" "$LOG_DIR"
sudo chown "$SVC_USER:$SVC_USER" "$LOG_DIR"

# Python virtual environment
sudo python3 -m venv "$INSTALL_DIR/venv"
sudo "$INSTALL_DIR/venv/bin/pip" install --upgrade pip requests

# Copy script
sudo cp ppdmwatch.py "$INSTALL_DIR/"
sudo chmod +x "$INSTALL_DIR/ppdmwatch.py"
sudo chown -R "$SVC_USER:$SVC_USER" "$INSTALL_DIR"

# Store credentials securely
sudo mkdir -p /etc/ppdmwatch
sudo chmod 700 /etc/ppdmwatch

read -rp "PPDM hostname: " PPDM_HOST
read -rp "PPDM username: " PPDM_USER
read -rsp "PPDM password: " PPDM_PASS; echo
read -rp "PPDM port [8443]: " PPDM_PORT
PPDM_PORT="${PPDM_PORT:-8443}"

sudo tee /etc/ppdmwatch/env > /dev/null <<EOF
PPDM_HOST=${PPDM_HOST}
PPDM_USER=${PPDM_USER}
PPDM_PASS=${PPDM_PASS}
PPDM_PORT=${PPDM_PORT}
EOF
sudo chmod 600 /etc/ppdmwatch/env

# Install and enable systemd service
sudo cp ppdmwatch.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ppdmwatch

echo ""
echo "=== Installation complete ==="
echo "Start:     sudo systemctl start ppdmwatch"
echo "Status:    sudo systemctl status ppdmwatch"
echo "Logs:      sudo journalctl -u ppdmwatch -f"
echo "Log file:  $LOG_DIR/ppdmwatch.log"
