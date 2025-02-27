#!/usr/bin/env python3
import logging
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Token del bot (inserito direttamente)
TOKEN = "8097932093:AAHpO7TnynwowBQHAoDVpG9e0oxGm7z9gFE"

# URL della web app (modifica se necessario)
WEB_APP_URL = "https://gianky-bot-test-f275065c7d33.herokuapp.com/static/index.html"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Apri Web App", web_app=WebAppInfo(url=WEB_APP_URL))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Clicca qui per aprire la web app:", reply_markup=reply_markup)

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    logging.info("Bot in esecuzione...")
    app.run_polling()

if __name__ == '__main__':
    main()
