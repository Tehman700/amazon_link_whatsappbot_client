#!/usr/bin/env bash
# One-time EC2 bootstrap for the WhatsApp adapter.
# Run on a fresh Ubuntu 22.04/24.04 instance as the default `ubuntu` user:
#   curl -fsSL https://raw.githubusercontent.com/Tehman700/amazon_link_whatsappbot_client/main/whatsapp-adapter/deploy/setup.sh | bash
set -euo pipefail

REPO="https://github.com/Tehman700/amazon_link_whatsappbot_client.git"
DIR="$HOME/amazon_link_whatsappbot_client"

echo "== Installing Node.js 20 =="
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs git

echo "== Installing pm2 =="
sudo npm install -g pm2

echo "== Cloning repo =="
if [ ! -d "$DIR" ]; then
  git clone "$REPO" "$DIR"
fi
cd "$DIR/whatsapp-adapter"

echo "== Installing dependencies =="
npm ci --omit=dev

if [ ! -f .env ]; then
  cp .env.example .env
  TOKEN=$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')
  sed -i "s/STATUS_TOKEN=change-me/STATUS_TOKEN=$TOKEN/" .env
  echo "== Generated .env (STATUS_TOKEN=$TOKEN) =="
fi

echo "== Starting under pm2 =="
pm2 start ecosystem.config.cjs
pm2 save
sudo env PATH=$PATH pm2 startup systemd -u "$USER" --hp "$HOME" | tail -1 | sudo bash || true
pm2 save

TOKEN=$(grep STATUS_TOKEN .env | cut -d= -f2)
IP=$(curl -s --max-time 5 http://checkip.amazonaws.com || echo "<instance-ip>")
echo ""
echo "=================================================================="
echo " Adapter is running."
echo " Pairing page:  http://$IP:4000/?token=$TOKEN"
echo " Open it in a browser and scan the QR from the bot's WhatsApp:"
echo "   WhatsApp -> Linked Devices -> Link a Device"
echo "=================================================================="
