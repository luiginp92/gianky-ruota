#!/usr/bin/env python3
import logging
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Token hardcoded come richiesto
TELEGRAM_BOT_TOKEN = "8097932093:AAHpO7TnynwowBQHAoDVpG9e0oxGm7z9gFE"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

async def start_telegram(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text(
            "Ciao, sono il bot Gianky Coin!\n"
            "Visita l'interfaccia web: https://gianky-bot-test-f275065c7d33.herokuapp.com/static/index.html"
        )
    else:
        logging.error("update.message is None in start_telegram")

async def main():
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_telegram))
    # Avvia il polling (close_loop=False evita di chiudere l'event loop)
    await application.run_polling(close_loop=False)

if __name__ == '__main__':
    asyncio.run(main())
