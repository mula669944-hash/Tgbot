# Telegram Python Bot Hoster (Android Termux)

A hosting platform operating entirely within Telegram that executes user-uploaded Python Telegram bots on an Android phone via Termux.

## Directory Structure
The hoster runs from:
`/storage/emulated/0/TelegramBotHost/`

## Termux Deployment Steps

1. **Install Termux & Termux:API** from F-Droid.
2. Grant Termux Android shared-storage permissions:
   ```bash
   termux-setup-storage