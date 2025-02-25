#!/usr/bin/env python3
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler

# Token hardcoded
TELEGRAM_BOT_TOKEN = "8097932093:AAHpO7TnynwowBQHAoDVpG9e0oxGm7z9gFE"

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

def start_telegram(update: Update, context):
    update.message.reply_text(
        "Ciao, sono il bot Gianky Coin!\n"
        "Visita l'interfaccia web: https://gianky-bot-test-f275065c7d33.herokuapp.com/static/index.html"
    )

def main():
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_telegram))
    # Avvia il polling in modalità sincrona nel thread principale
    application.run_polling()

if __name__ == '__main__':
    main()
