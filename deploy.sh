#!/bin/bash
# deploy.sh — One-shot deployment script for Ubuntu / Oracle Cloud / Raspberry Pi
# Run as: bash deploy.sh
# Tested on: Ubuntu 20.04+, Raspberry Pi OS (64-bit), Debian 11+

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"
SERVICE_NAME="streak-guardian"

echo "═══════════════════════════════════════════"
echo "  🛡️  Streak Guardian — Deployment Script"
echo "═══════════════════════════════════════════"
echo ""

# ── 1. System dependencies ────────────────────────────────────────────────────
echo "[1/6] Installing system dependencies …"
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3 python3-pip python3-venv \
    chromium-browser chromium-driver \
    libglib2.0-0 libnss3 libdbus-1-3 libatk1.0-0 \
    libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 || true
echo "✅ System dependencies installed"

# ── 2. Python virtual environment ────────────────────────────────────────────
echo "[2/6] Creating Python virtual environment …"
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip --quiet
echo "✅ Virtual environment ready"

# ── 3. Python dependencies ────────────────────────────────────────────────────
echo "[3/6] Installing Python dependencies …"
pip install -r "$PROJECT_DIR/requirements.txt" --quiet
echo "✅ Python dependencies installed"

# ── 4. Playwright browser ─────────────────────────────────────────────────────
echo "[4/6] Installing Playwright Chromium …"
python -m playwright install chromium
python -m playwright install-deps chromium || true
echo "✅ Playwright Chromium installed"

# ── 5. Directory permissions ──────────────────────────────────────────────────
echo "[5/6] Creating runtime directories …"
mkdir -p "$PROJECT_DIR/logs" "$PROJECT_DIR/screenshots" "$PROJECT_DIR/database"
chmod 750 "$PROJECT_DIR/logs" "$PROJECT_DIR/screenshots" "$PROJECT_DIR/database"
echo "✅ Directories ready"

# ── 6. systemd service ────────────────────────────────────────────────────────
echo "[6/6] Setting up systemd service …"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# Update WorkingDirectory and ExecStart in the service file
sudo cp "$PROJECT_DIR/streak-guardian.service" "$SERVICE_FILE"
sudo sed -i "s|WorkingDirectory=.*|WorkingDirectory=$PROJECT_DIR|" "$SERVICE_FILE"
sudo sed -i "s|ExecStart=.*|ExecStart=$VENV_DIR/bin/python $PROJECT_DIR/main.py|" "$SERVICE_FILE"
sudo sed -i "s|User=ubuntu|User=$(whoami)|" "$SERVICE_FILE"

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
echo "✅ systemd service configured"

echo ""
echo "═══════════════════════════════════════════"
echo "  ✅ Deployment complete!"
echo "═══════════════════════════════════════════"
echo ""
echo "Next steps:"
echo "  1. Copy and fill in your .env:"
echo "       cp $PROJECT_DIR/.env.example $PROJECT_DIR/.env"
echo "       nano $PROJECT_DIR/.env"
echo ""
echo "  2. Test your configuration:"
echo "       source $VENV_DIR/bin/activate"
echo "       python $PROJECT_DIR/main.py --test-notify"
echo "       python $PROJECT_DIR/main.py --check-now"
echo ""
echo "  3. Start the service:"
echo "       sudo systemctl start $SERVICE_NAME"
echo "       sudo systemctl status $SERVICE_NAME"
echo ""
echo "  4. View logs:"
echo "       journalctl -u $SERVICE_NAME -f"
echo ""
echo "  5. Dashboard: http://$(hostname -I | awk '{print $1}'):8000"
echo ""
