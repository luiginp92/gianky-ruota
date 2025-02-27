#!/usr/bin/env python3
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest

TOKEN = "TELEGRAM_BOT_TOKEN = "8097932093:AAHpO7TnynwowBQHAoDVpG9e0oxGm7z9gFE"  # token reale
WEB_APP_URL = "https://gianky-bot-test-f275065c7d33.herokuapp.com/static/index.html"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
      [
        InlineKeyboardButton("Apri Mini App", web_app=WebAppInfo(url=WEB_APP_URL))
      ]
    ]
    reply_markup = InlineKeyboardMarkup(kb)
    await update.message.reply_text("Clicca qui per aprire la mini app:", reply_markup=reply_markup)

def main():
    request = HTTPXRequest(connect_timeout=30, read_timeout=30)
    app = ApplicationBuilder().token(TOKEN).request(request).build()
    app.add_handler(CommandHandler("start", start))
    logging.info("Bot in esecuzione...")
    app.run_polling()

if __name__ == "__main__":
    main()
