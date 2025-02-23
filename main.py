#!/usr/bin/env python3
"""
Gianky Coin Bot - main.py
--------------------------
Questo file implementa un bot Telegram che:
  - Collega il wallet (/connect)
  - Mostra la ruota statica (/ruota) una volta e mantiene un contatore dei tiri disponibili.
  - Al click sul pulsante "Gira la ruota!" consuma uno spin, calcola il premio e aggiorna il messaggio.
  - Ogni giorno (secondo il fuso orario italiano) è disponibile un giro gratuito; extra spin possono essere acquistati.
  - Se non ci sono spin disponibili, viene mostrato un messaggio appropriato.
"""

#######################################
# IMPORTAZIONI E CONFIGURAZIONI INIZIALI
#######################################

import logging
import random
import datetime
import os
import io
import asyncio

import pytz  # Per il fuso orario italiano

from web3 import Web3
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.request import HTTPXRequest

from database import Session, User, PremioVinto

#######################################
# CONFIGURAZIONE DEL LOGGING
#######################################

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

#######################################
# COSTANTI E CONFIGURAZIONI DEL BOT
#######################################

TOKEN = "8097932093:AAHpO7TnynwowBQHAoDVpG9e0oxGm7z9gFE"
IMAGE_PATH = "ruota.png"  # Immagine statica della ruota

POLYGON_RPC = "https://polygon-rpc.com"
w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
WALLET_DISTRIBUZIONE = "0xBc0c054066966a7A6C875981a18376e2296e5815"
CONTRATTO_GKY = "0x370806781689E670f85311700445449aC7C3Ff7a"

PRIVATE_KEY = os.getenv("PRIVATE_KEY_GKY")
if not PRIVATE_KEY:
    raise ValueError("❌ Errore: la chiave privata non è impostata.")

#######################################
# CACHING DEL FILE DI IMMAGINE STATICA
#######################################

if os.path.exists(IMAGE_PATH):
    with open(IMAGE_PATH, "rb") as f:
        STATIC_IMAGE_BYTES = f.read()
else:
    STATIC_IMAGE_BYTES = None
    logging.error("File statico non trovato: ruota.png")

#######################################
# VARIABILE GLOBALE PER TX DUPLICATI
#######################################

USED_TX = set()

#######################################
# FUNZIONI UTILI: GAS, TRANSAZIONI, PREMI
#######################################

def get_dynamic_gas_price():
    try:
        base = w3.eth.gas_price
        safe = int(base * 1.2)
        logging.info(f"⛽ Gas Price: {w3.from_wei(base, 'gwei')} -> {w3.from_wei(safe, 'gwei')}")
        return safe
    except Exception as e:
        logging.error(f"Errore nel gas price: {e}")
        return w3.to_wei('50', 'gwei')

def invia_token(destinatario, quantita):
    if not w3.is_connected():
        logging.error("Blockchain non connessa.")
        return False
    gas_price = get_dynamic_gas_price()
    contratto = w3.eth.contract(address=CONTRATTO_GKY, abi=[
        {
            "constant": False,
            "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}],
            "name": "transfer",
            "outputs": [{"name": "", "type": "bool"}],
            "payable": False,
            "stateMutability": "nonpayable",
            "type": "function",
        }
    ])
    tx = contratto.functions.transfer(destinatario, quantita * 10**18).build_transaction({
        'from': WALLET_DISTRIBUZIONE,
        'nonce': w3.eth.get_transaction_count(WALLET_DISTRIBUZIONE),
        'gas': 100000,
        'gasPrice': gas_price,
    })
    signed = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    logging.info(f"Token inviati: {quantita} GKY, TX: {tx_hash.hex()}")
    return True

def verifica_transazione_gky(user_address, tx_hash, cost):
    try:
        tx = w3.eth.get_transaction(tx_hash)
        if tx["to"].lower() != CONTRATTO_GKY.lower():
            logging.error("TX non destinata al contratto GKY.")
            return False
        contract = w3.eth.contract(address=CONTRATTO_GKY, abi=[
            {
                "constant": False,
                "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}],
                "name": "transfer",
                "outputs": [{"name": "", "type": "bool"}],
                "payable": False,
                "stateMutability": "nonpayable",
                "type": "function",
            }
        ])
        try:
            func_obj, params = contract.decode_function_input(tx.input)
        except Exception as decode_error:
            logging.error(f"Decodifica TX fallita: {decode_error}")
            return False
        if func_obj.fn_name != "transfer":
            logging.error("TX non chiama transfer.")
            return False
        if params.get("_to", "").lower() != WALLET_DISTRIBUZIONE.lower():
            logging.error("TX non invia al portafoglio di distribuzione.")
            return False
        token_amount = params.get("_value", 0)
        if token_amount < cost * 10**18:
            logging.error(f"Importo insufficiente: {w3.from_wei(token_amount, 'ether')} vs {cost}")
            return False
        return True
    except Exception as e:
        logging.error(f"Errore verifica TX: {e}")
        return False

def get_prize():
    """
    Calcola il premio secondo la seguente distribuzione (percentuali):
      - NFT BASISC: 0.02%
      - NFT STARTER: 0.04%
      - Normal prizes totali: 99.0%, così suddivisi:
            NO PRIZE: 30%
            10 GKY: 25%
            20 GKY: 20%
            50 GKY: 10%
            100 GKY: 7%
            250 GKY: 4%
            500 GKY: 2%
            1000 GKY: 1%
    """
    r = random.random() * 100  # Genera un numero tra 0 e 100
    if r < 0.02:
        return "NFT BASISC"
    elif r < 0.02 + 0.04:
        return "NFT STARTER"
    else:
        r2 = r - 0.06  # r2 varia da 0 a 99
        if r2 < 30:
            return "NO PRIZE"
        elif r2 < 30 + 25:
            return "10 GKY"
        elif r2 < 55 + 20:  # 75
            return "20 GKY"
        elif r2 < 75 + 10:  # 85
            return "50 GKY"
        elif r2 < 85 + 7:   # 92
            return "100 GKY"
        elif r2 < 92 + 4:   # 96
            return "250 GKY"
        elif r2 < 96 + 2:   # 98
            return "500 GKY"
        else:
            return "1000 GKY"

#######################################
# COMANDI DEL BOT
#######################################

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎉 Benvenuto in Gianky Coin!\n\n"
        "Usa /connect <wallet_address> per collegare il wallet,\n"
        "usa /ruota per visualizzare la ruota e il contatore dei tiri disponibili,\n"
        "/buyspins per acquistare extra tiri."
    )

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.message.from_user.id)
    if context.args:
        wallet_address = context.args[0]
        if not Web3.is_address(wallet_address):
            await update.message.reply_text("❌ Indirizzo non valido.")
            return
        session = Session()
        try:
            user = session.query(User).filter_by(telegram_id=telegram_id).first()
            if not user:
                user = User(telegram_id=telegram_id, wallet_address=wallet_address, extra_spins=0)
                session.add(user)
            else:
                user.wallet_address = wallet_address
            session.commit()
            await update.message.reply_text("✅ Wallet collegato!")
        except Exception as e:
            logging.error(f"Errore connessione wallet: {e}")
            session.rollback()
            await update.message.reply_text("❌ Errore durante la connessione del wallet.")
        finally:
            session.close()
    else:
        await update.message.reply_text("❌ Usa: /connect <wallet_address>")

async def ruota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comando per mostrare la ruota statica con il contatore dei tiri disponibili.
    Il contatore viene calcolato come: se l'utente non ha giocato oggi (fuso italiano),
    il giro gratuito è disponibile (1 tiro) + extra_spins; altrimenti, solo extra_spins.
    """
    telegram_id = str(update.message.from_user.id)
    session = Session()
    try:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
    except Exception as e:
        logging.error(f"Errore recupero utente: {e}")
        user = None
    finally:
        session.close()
    if not user or not user.wallet_address:
        await update.message.reply_text("⚠️ Collega il wallet con /connect")
        return

    # Calcola i tiri disponibili in base al fuso orario italiano
    italy_tz = pytz.timezone("Europe/Rome")
    now_italy = datetime.datetime.now(italy_tz)
    if user.last_play_date is None or user.last_play_date.astimezone(italy_tz).date() != now_italy.date():
        available = 1 + (user.extra_spins or 0)
    else:
        available = user.extra_spins or 0

    caption = f"🎰 Ruota pronta! Tiri disponibili: {available}\nPremi il pulsante per girarla."
    keyboard = [[InlineKeyboardButton("🎡 Gira la ruota!", callback_data="spin")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if STATIC_IMAGE_BYTES:
        photo = InputFile(io.BytesIO(STATIC_IMAGE_BYTES), filename="ruota.png")
        await update.message.reply_photo(
            photo=photo,
            caption=caption,
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text("⚠️ Immagine della ruota non trovata.")

async def buyspins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.message.from_user.id)
    session = Session()
    try:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if not user or not user.wallet_address:
            await update.message.reply_text("⚠️ Collega il wallet con /connect")
            return
        if not context.args:
            await update.message.reply_text("❌ Specifica il numero di tiri extra (1 o 3).")
            return
        try:
            num_spins = int(context.args[0])
        except:
            await update.message.reply_text("❌ Numero di tiri deve essere un intero.")
            return
        if num_spins == 1:
            cost = 50
        elif num_spins == 3:
            cost = 125
        else:
            await update.message.reply_text("❌ Puoi acquistare solo 1 o 3 tiri extra.")
            return
        await update.message.reply_text(
            f"✅ Per acquistare {num_spins} tiri extra, trasferisci {cost} GKY al portafoglio:\n**{WALLET_DISTRIBUZIONE}**\nUsa /confirmbuy <tx_hash> <num>"
        )
    except Exception as e:
        logging.error(f"Errore in buyspins: {e}")
        await update.message.reply_text("❌ Errore durante l'acquisto dei tiri extra.")
    finally:
        session.close()

async def confirmbuy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.message.from_user.id)
    session = Session()
    try:
        if not context.args or len(context.args) < 2:
            await update.message.reply_text("❌ Usa: /confirmbuy <tx_hash> <num>")
            return
        tx_hash = context.args[0]
        if tx_hash in USED_TX:
            await update.message.reply_text("❌ Questa transazione è già stata usata per l'acquisto di extra tiri.")
            return
        try:
            num_spins = int(context.args[1])
        except:
            await update.message.reply_text("❌ Numero di tiri deve essere un intero.")
            return
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if not user or not user.wallet_address:
            await update.message.reply_text("⚠️ Collega il wallet con /connect")
            return
        if num_spins == 1:
            cost = 50
        elif num_spins == 3:
            cost = 125
        else:
            await update.message.reply_text("❌ Solo 1 o 3 tiri extra sono ammessi.")
            return
        if verifica_transazione_gky(user.wallet_address, tx_hash, cost):
            user.extra_spins = (user.extra_spins or 0) + num_spins
            session.commit()
            USED_TX.add(tx_hash)
            await update.message.reply_text(f"✅ Acquisto confermato! Extra tiri disponibili: {user.extra_spins}")
        else:
            await update.message.reply_text("❌ Transazione non valida o importo insufficiente.")
    except Exception as e:
        logging.error(f"Errore in confirmbuy: {e}")
        await update.message.reply_text("❌ Errore durante la conferma degli extra tiri.")
    finally:
        session.close()

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Callback per "Gira la ruota!".
    - Mostra il risultato del giro e aggiorna il contatore dei tiri disponibili.
    - Il messaggio della ruota viene aggiornato (modificando la didascalia) per mostrare in tempo reale i tiri disponibili.
    """
    query = update.callback_query
    try:
        await query.answer()
    except Exception as e:
        logging.error(f"Errore in query.answer(): {e}")
    telegram_id = str(query.from_user.id)
    session = Session()
    try:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if not user or not user.wallet_address:
            await query.edit_message_caption("⚠️ Collega il wallet con /connect")
            return

        # Imposta il fuso orario italiano
        italy_tz = pytz.timezone("Europe/Rome")
        now_italy = datetime.datetime.now(italy_tz)

        # Calcola spin disponibili: se non ha giocato oggi, il giro gratuito è disponibile (1) + extra_spins; altrimenti, solo extra_spins.
        if user.last_play_date is None or user.last_play_date.astimezone(italy_tz).date() != now_italy.date():
            available = 1 + (user.extra_spins or 0)
            # Consuma il giro gratuito aggiornando last_play_date
            user.last_play_date = now_italy
            session.commit()
        else:
            available = user.extra_spins or 0
            if available > 0:
                user.extra_spins -= 1
                session.commit()
                available -= 1
            else:
                await query.edit_message_caption("⚠️ Hai esaurito i tiri disponibili per oggi. Acquista extra tiri con /buyspins.")
                return

        # Calcola il premio
        prize = get_prize()
        if prize == "NO PRIZE":
            result_text = "😔 Nessun premio vinto. Riprova!"
        elif "GKY" in prize:
            amount = int(prize.split(" ")[0])
            if invia_token(user.wallet_address, amount):
                result_text = f"🎉 Hai vinto {amount} GKY!"
            else:
                result_text = "❌ Errore nell'invio dei token."
        else:
            result_text = f"🎉 Hai vinto: {prize}!"
            premio_record = PremioVinto(telegram_id=telegram_id, wallet=user.wallet_address, premio=prize)
            session.add(premio_record)
            session.commit()

        # Ricalcola spin disponibili dopo il consumo
        if user.last_play_date.astimezone(italy_tz).date() != now_italy.date():
            new_available = 1 + (user.extra_spins or 0)
        else:
            new_available = user.extra_spins or 0

        new_caption = f"{result_text}\n\n🎰 Ruota pronta! Tiri disponibili: {new_available}"
        try:
            await query.edit_message_caption(caption=new_caption)
        except Exception as e:
            logging.error(f"Errore nell'aggiornamento della didascalia: {e}")
            await query.message.reply_text(new_caption)
    except Exception as e:
        logging.error(f"Errore nel callback della ruota: {e}")
        try:
            await query.edit_message_caption("❌ Errore durante il giro della ruota.")
        except Exception:
            await query.message.reply_text("❌ Errore durante il giro della ruota.")
    finally:
        session.close()

#######################################
# FUNZIONE PRINCIPALE
#######################################

def main():
    request = HTTPXRequest(connect_timeout=30, read_timeout=30)
    app = ApplicationBuilder().token(TOKEN).request(request).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("connect", connect))
    app.add_handler(CommandHandler("ruota", ruota))
    app.add_handler(CommandHandler("buyspins", buyspins))
    app.add_handler(CommandHandler("confirmbuy", confirmbuy))
    app.add_handler(CallbackQueryHandler(button))
    logging.info("✅ Bot in esecuzione...")
    app.run_polling()

if __name__ == '__main__':
    main()
