#!/data/data/com.termux/files/usr/bin/bash

BASE_DIR="/storage/emulated/0/TelegramBotHost"

echo "=========================================="
echo " Starting Telegram Bot Hoster on Termux   "
echo "=========================================="

# 1. Acquire Wake Lock to prevent Android OS deep sleep
termux-wake-lock

# 2. Check storage permission
if [ ! -d "/storage/emulated/0" ]; then
    echo "[-] Requesting Storage Permissions..."
    termux-setup-storage
    sleep 3
fi

# 3. Create Root Directory
mkdir -p "$BASE_DIR"
cd "$BASE_DIR" || exit 1

# 4. Check dependencies
if ! command -v python &> /dev/null; then
    echo "[-] Installing Python and dependencies..."
    pkg update -y && pkg install python clang -y
fi

pip install --upgrade pip
pip install -r requirements.txt

# 5. Run the Hoster
echo "[+] Starting main.py..."
python -u main.py