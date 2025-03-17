#!/usr/bin/env python3
import logging
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest

# Importa il database per aggiornare eventuali referral
from database import Session, User, init_db

# Inizializza il database (crea le tabelle se non esistono)
init_db()

# Usa il token esatto (senza spazi o modifiche)
TOKEN = "8097932093:AAHpO7TnynwowBQHAoDVpG9e0oxGm7z9gFE"
# URL della mini app
WEB_APP_URL = "https://gianky-bot-test-f275065c7d33.herokuapp.com/static/index.html"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    # Gestisci il referral se il comando contiene un referral code (es. /start ref_0x123... )
    if "ref_" in text:
        try:
            ref_code = text.split("ref_")[1].strip()
            session = Session()
            referrer = session.query(User).filter(User.wallet_address.ilike(ref_code)).first()
            if referrer:
                # Aggiungi 2 extra spin al referrer
                referrer.extra_spins += 2
                session.commit()
                await update.message.reply_text("Hai ricevuto 2 giri extra per la referral!")
            session.close()
        except Exception as e:
            logging.error(f"Errore nel processing referral: {e}")
    keyboard = [
        [InlineKeyboardButton("Apri Mini App", web_app=WebAppInfo(url=WEB_APP_URL))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Clicca qui per aprire la mini app:", reply_markup=reply_markup)

async def giankyadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Se vuoi abilitare anche il comando admin per visualizzare report globali,
    # assicurati che solo gli admin possano usarlo (questa parte va personalizzata).
    from database import Session, GlobalCounter
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
