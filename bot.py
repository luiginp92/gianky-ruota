#!/usr/bin/env python3
import logging
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Imposta il token direttamente (o meglio, usalo da variabile d'ambiente se possibile)
TELEGRAM_BOT_TOKEN = "8097932093:AAHpO7TnynwowBQHAoDVpG9e0oxGm7z9gFE"

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

async def start_telegram(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Ciao, sono il bot Gianky Coin!\n"
        "Visita l'interfaccia web: https://gianky-bot-test-f275065c7d33.herokuapp.com/static/index.html"
    )

async def main():
    bot_app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start_telegram))
    # Avvia il polling nel thread principale (questo file verrà eseguito da solo)
    await bot_app.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
