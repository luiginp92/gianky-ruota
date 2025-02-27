#!/usr/bin/env python3
import logging
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest

# Token del bot
TOKEN = "8097932093:AAHpO7TnynwowBQHAoDVpG9e0oxGm7z9gFE"

# URL che punta direttamente a index.html (senza cartella /static)
# Esempio: https://gianky-bot-test-f275065c7d33.herokuapp.com/
WEB_APP_URL = "https://gianky-bot-test-f275065c7d33.herokuapp.com/"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Crea un pulsante che apre la mini app all'indirizzo index.html
    keyboard = [
        [InlineKeyboardButton("Apri Mini App", web_app=WebAppInfo(url=WEB_APP_URL))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        text="Clicca qui per aprire la mini app:",
        reply_markup=reply_markup
    )

def main():
    request = HTTPXRequest(connect_timeout=30, read_timeout=30)
    app = ApplicationBuilder().token(TOKEN).request(request).build()

    # Gestore del comando /start
    app.add_handler(CommandHandler("start", start))

    logging.info("Bot in esecuzione...")
    app.run_polling()

if __name__ == '__main__':
    main()
