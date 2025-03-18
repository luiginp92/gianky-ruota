#!/usr/bin/env python3
import logging
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest

from database import Session, GlobalCounter, init_db

init_db()

# Token e URL della mini app
TOKEN = "8097932093:AAHpO7TnynwowBQHAoDVpG9e0oxGm7z9gFE"
BASE_WEB_APP_URL = "https://gianky-bot-test-f275065c7d33.herokuapp.com/static/index.html"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Estrai eventuali parametri dal comando /start
    # Aspettiamo un formato del tipo: "/start ref_0x1234..."
    message_text = update.message.text if update.message.text else ""
    referral_param = ""
    parts = message_text.split()
    if len(parts) > 1 and parts[1].startswith("ref_"):
        # Rimuoviamo "ref_" per ottenere il wallet referenziato
        referral_code = parts[1][4:]
        referral_param = f"?ref={referral_code}"
        logging.info(f"Referral rilevato: {referral_code}")
    else:
        logging.info("Nessun referral rilevato nel comando /start")
    
    final_url = BASE_WEB_APP_URL + referral_param if referral_param else BASE_WEB_APP_URL

    keyboard = [
        [InlineKeyboardButton("Apri Mini App", web_app=WebAppInfo(url=final_url))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Clicca qui per aprire la mini app:", reply_markup=reply_markup)

async def giankyadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = Session()
    try:
        counter = session.query(GlobalCounter).first()
        if counter is None:
            report_text = "Nessun dato disponibile."
        else:
            total_in = counter.total_in
            total_out = counter.total_out
            balance = total_in - total_out
            report_text = (
                f"📊 **Report GiankyCoin** 📊\n\n"
                f"**Entrate Totali:** {total_in} GKY\n"
                f"**Uscite Totali:** {total_out} GKY\n"
                f"**Bilancio:** {balance} GKY"
            )
        await update.message.reply_text(report_text, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Errore in giankyadmin: {e}")
        await update.message.reply_text("Errore nel recupero dei dati.")
    finally:
        session.close()

def main():
    request = HTTPXRequest(connect_timeout=30, read_timeout=30)
    app = ApplicationBuilder().token(TOKEN).request(request).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("giankyadmin", giankyadmin))
    logging.info("Bot in esecuzione...")
    app.run_polling()

if __name__ == '__main__':
    main()
