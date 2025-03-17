#!/usr/bin/env python3
import logging
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest

# Importa la sessione e le funzioni per il database
from database import Session, GlobalCounter, init_db

# Inizializza il database (crea le tabelle se non esistono)
init_db()

# Usa il token esatto (senza spazi o modifiche)
TOKEN = "8097932093:AAHpO7TnynwowBQHAoDVpG9e0oxGm7z9gFE"
# URL della mini app (modifica se necessario)
WEB_APP_URL = "https://gianky-bot-test-f275065c7d33.herokuapp.com/static/index.html"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Apri Mini App", web_app=WebAppInfo(url=WEB_APP_URL))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Clicca qui per aprire la mini app:", reply_markup=reply_markup)

async def giankyadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comando per mostrare il report globale delle entrate (buy spins) e uscite (premi vinti)
    del wallet di distribuzione. Il report è aggiornato in tempo reale.
    """
    session = Session()
    try:
        counter = session.query(GlobalCounter).first()
        if counter is None:
            report_text = "Nessun dato disponibile ancora."
        else:
            total_in = counter.total_in
            total_out = counter.total_out
            balance = total_in - total_out
            report_text = (
                f"📊 *Report Globali GiankyCoin:*\n\n"
                f"*Entrate totali:* {total_in:.2f} GKY\n"
                f"*Uscite totali:* {total_out:.2f} GKY\n"
                f"*Bilancio:* {balance:.2f} GKY"
            )
        await update.message.reply_text(report_text, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Errore in giankyadmin: {e}")
        await update.message.reply_text("Errore durante la generazione del report.")
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
