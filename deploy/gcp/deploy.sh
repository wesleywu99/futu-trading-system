#!/bin/bash
# ============================================================
# Futu Trading System - Google Cloud Deployment Script
# ============================================================
# Usage:
#   chmod +x deploy.sh
#   ./deploy.sh --account YOUR_FUTU_ACCOUNT --password YOUR_FUTU_PASSWORD
#   ./deploy.sh --account YOUR_FUTU_ACCOUNT --password-md5 YOUR_MD5_HASH
# ============================================================

set -e

# --- Parse arguments ---
ACCOUNT=""
PASSWORD=""
PASSWORD_MD5=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --account)
            ACCOUNT="$2"
            shift 2
            ;;
        --password)
            PASSWORD="$2"
            shift 2
            ;;
        --password-md5)
            PASSWORD_MD5="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 --account ACCOUNT --password PASSWORD"
            echo "       $0 --account ACCOUNT --password-md5 MD5_HASH"
            exit 1
            ;;
    esac
done

if [ -z "$ACCOUNT" ]; then
    echo "Error: --account is required"
    exit 1
fi

if [ -z "$PASSWORD_MD5" ] && [ -z "$PASSWORD" ]; then
    echo "Error: --password or --password-md5 is required"
    exit 1
fi

# Compute MD5 from plaintext if needed
if [ -z "$PASSWORD_MD5" ]; then
    PASSWORD_MD5=$(echo -n "$PASSWORD" | md5sum | awk '{print $1}')
    echo "[INFO] Computed MD5 from plaintext password"
fi

DEPLOY_USER=$(whoami)
DEPLOY_DIR="/home/$DEPLOY_USER"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "============================================================"
echo "  Futu Trading System - GCP Deployment"
echo "============================================================"
echo "  User:     $DEPLOY_USER"
echo "  Home:     $DEPLOY_DIR"
echo "  Account:  $ACCOUNT"
echo "============================================================"

# --- Step 1: System packages ---
echo ""
echo "[Step 1/7] Installing system packages..."
sudo apt update
sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git telnet curl

# --- Step 2: Create swap ---
echo ""
echo "[Step 2/7] Configuring 2GB swap..."
if [ ! -f /swapfile ]; then
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    echo "[OK] Swap created and enabled"
else
    echo "[SKIP] Swap already exists"
fi

# --- Step 3: Download and install Futu OpenD ---
echo ""
echo "[Step 3/7] Installing Futu OpenD (command line)..."
OPEND_DIR="$DEPLOY_DIR/futu-opend"
mkdir -p "$OPEND_DIR"

if [ ! -f "$OPEND_DIR/FutuOpenD" ]; then
    echo "[INFO] Downloading OpenD for Ubuntu..."
    curl -L "https://www.futunn.com/download/fetch-lasted-link?name=opend-ubuntu" \
         -o "$OPEND_DIR/FutuOpenD.tar.gz"

    echo "[INFO] Extracting..."
    tar -xzf "$OPEND_DIR/FutuOpenD.tar.gz" -C "$OPEND_DIR"

    # Find the extracted directory and move contents up
    EXTRACTED_DIR=$(find "$OPEND_DIR" -maxdepth 1 -type d -name "FutuOpenD_*" | head -1)
    if [ -n "$EXTRACTED_DIR" ] && [ "$EXTRACTED_DIR" != "$OPEND_DIR" ]; then
        cp -r "$EXTRACTED_DIR"/* "$OPEND_DIR/"
        rm -rf "$EXTRACTED_DIR"
    fi

    chmod +x "$OPEND_DIR/FutuOpenD"
    rm -f "$OPEND_DIR/FutuOpenD.tar.gz"
    echo "[OK] OpenD installed"
else
    echo "[SKIP] OpenD already installed"
fi

# --- Step 4: Configure FutuOpenD.xml ---
echo ""
echo "[Step 4/7] Configuring FutuOpenD.xml..."
cat > "$OPEND_DIR/FutuOpenD.xml" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<config>
    <ip>127.0.0.1</ip>
    <api_port>11111</api_port>
    <login_account>$ACCOUNT</login_account>
    <login_pwd_md5>$PASSWORD_MD5</login_pwd_md5>
    <lang>chs</lang>
    <log_level>info</log_level>
    <telnet_ip>127.0.0.1</telnet_ip>
    <telnet_port>22222</telnet_port>
</config>
EOF
echo "[OK] FutuOpenD.xml configured"

# --- Step 5: Setup Python environment ---
echo ""
echo "[Step 5/7] Setting up Python environment..."
PROJECT_DIR="$DEPLOY_DIR/futu-trading-system"

if [ ! -d "$PROJECT_DIR/venv" ]; then
    python3 -m venv "$PROJECT_DIR/venv"
fi

source "$PROJECT_DIR/venv/bin/activate"
pip install --upgrade pip
pip install futu-api pyyaml pandas numpy openpyxl matplotlib
echo "[OK] Python dependencies installed"

# --- Step 6: Install systemd services ---
echo ""
echo "[Step 6/7] Installing systemd services..."

# OpenD service
sudo tee /etc/systemd/system/futu-opend.service > /dev/null << EOF
[Unit]
Description=Futu OpenD Gateway
After=network.target

[Service]
Type=simple
User=$DEPLOY_USER
WorkingDirectory=$OPEND_DIR
ExecStart=$OPEND_DIR/FutuOpenD
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Trading system service
sudo tee /etc/systemd/system/futu-trading.service > /dev/null << EOF
[Unit]
Description=Futu Trading System
After=futu-opend.service
Requires=futu-opend.service

[Service]
Type=simple
User=$DEPLOY_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/venv/bin/python -m src.main
Restart=always
RestartSec=30
Environment=FUTU_CONFIG_PATH=config/config.yaml

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
echo "[OK] systemd services installed"

# --- Step 7: Start OpenD ---
echo ""
echo "[Step 7/7] Starting Futu OpenD..."
sudo systemctl enable futu-opend
sudo systemctl start futu-opend
echo "[OK] OpenD started"
echo ""
echo "============================================================"
echo "  Deployment Complete!"
echo "============================================================"
echo ""
echo "  Next steps:"
echo "  1. Check OpenD login status:"
echo "     sudo journalctl -u futu-opend -f"
echo ""
echo "  2. If SMS verification is needed:"
echo "     telnet 127.0.0.1 22222"
echo "     input_phone_verify_code -code=YOUR_CODE"
echo ""
echo "  3. After OpenD login succeeds, start trading system:"
echo "     sudo systemctl enable futu-trading"
echo "     sudo systemctl start futu-trading"
echo ""
echo "  4. Monitor trading system:"
echo "     sudo journalctl -u futu-trading -f"
echo ""
echo "  Useful commands:"
echo "     sudo systemctl status futu-opend"
echo "     sudo systemctl status futu-trading"
echo "     sudo systemctl restart futu-opend"
echo "     sudo systemctl restart futu-trading"
echo "============================================================"
