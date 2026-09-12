#!/bin/bash
set -e

echo "=== Dalaman Airport Suite Bot Kurulumu Basliyor ==="

# Paketleri guncelle ve gerekli araclari yukle
apt update -y
apt install -y python3 python3-pip python3-venv git curl

# Klasor yapisi
APP_DIR="/opt/dalaman-suite-bot"
mkdir -p $APP_DIR

# Dosyalari tasi (eger baska yerden calistiriliyorsa)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
if [ "$SCRIPT_DIR" != "$APP_DIR" ]; then
    cp -r $SCRIPT_DIR/* $APP_DIR/
fi

cd $APP_DIR

# Python Sanal Ortami (venv) olustur
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt

# Systemd servisini kaydet ve baslat
cp service/dalaman-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable dalaman-bot
systemctl restart dalaman-bot

IP=$(hostname -I | awk '{print $1}')
echo "========================================================"
echo "Kurulum Basariyla Tamamlandi!"
echo "Web Arayuzunuze su adresten erisebilirsiniz:"
echo "👉 http://$IP:8000"
echo "========================================================"
