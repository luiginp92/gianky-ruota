#!/usr/bin/env python3
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackContext

# Token hardcoded come richiesto
TELEGRAM_BOT_TOKEN = "8097932093:AAHpO7TnynwowBQHAoDVpG9e0oxGm7z9gFE"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

async def start_telegram(update: Update, context: CallbackContext):
    message = update.effective_message
    if message:
        # Crea un pulsante che porta all'interfaccia web
        keyboard = [[InlineKeyboardButton("Gioca Ora", url="https://gianky-bot-test-f275065c7d33.herokuapp.com/static/index.html")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.reply_text(
            "Benvenuto in GiankyCoin - La Ruota della Fortuna ti aspetta!\n\n"
            "Premi il pulsante qui sotto per girare la ruota e vincere premi fantastici!",
            reply_markup=reply_markup
        )
    else:
        logging.error("Nessun messaggio efficace trovato in update")

def main():
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_telegram))
    application.run_polling()

if __name__ == '__main__':
    main()
