#!/usr/bin/env python3
"""
Gianky Coin Bot - main.py
--------------------------
Questo file implementa un bot Telegram che:
  - Collega il wallet (/connect)
  - Mostra la ruota statica (/ruota) con un contatore aggiornato dei tiri disponibili.
  - Al click sul pulsante "Gira la ruota!" consuma uno spin, calcola il premio e aggiorna il messaggio.
  - Ogni giorno (fuso orario italiano) è disponibile un giro gratuito; extra spin possono essere acquistati.
  - È disponibile una task settimanale di condivisione per vincere 1 giro extra.
  - Gli utenti possono ottenere un link referral (/referral) e, se un nuovo utente si registra tramite quel link, l’invitante riceve 2 extra spin.
  - Il comando /giankyadmin mostra un report globale delle entrate e uscite.
  - Un task automatico controlla in background le transazioni in arrivo sul contratto (CONTRATTO_GKY)
    e accredita extra spin automaticamente.
  - La funzione /confirmbuy rimane come riserva manuale.
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
import pytz

from web3 import Web3
# La riga seguente è stata rimossa perché causa errore:
# from web3.middleware.geth_poa import geth_poa_middleware

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

from database import Session, User, PremioVinto, GlobalCounter

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
BOT_USERNAME = "giankytestbot"  # Username del bot (senza @)

POLYGON_RPC = "https://polygon-rpc.com"
w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
# Rimuovi il middleware POA, se non necessario:
# w3.middleware_onion.inject(geth_poa_middleware, layer=0)
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
# VARIABILE GLOBALE PER TX DUPLICATI E TASK AUTOMATICO
#######################################

USED_TX = set()
LAST_BLOCK = None

#######################################
# FUNZIONI UTILI: GAS, TRANSAZIONI, PREMI, AGGIORNAMENTO CONTATORI
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
    contratto = w3.eth.contract(address=CONTRATTO_GKY, abi=[{
        "constant": False,
        "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function",
    }])
    tx = contratto.functions.transfer(destinatario, quantita * 10**18).build_transaction({
        'from': WALLET_DISTRIBUZIONE,
        'nonce': w3.eth.get_transaction_count(WALLET_DISTRIBUZIONE),
        'gas': 100000,
        'gasPrice': gas_price,
    })
    signed = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    logging.info(f"Token inviati: {quantita} GKY, TX: {tx_hash.hex()}")
    # Aggiorna il contatore globale per uscite
    session = Session()
    try:
        counter = session.query(GlobalCounter).first()
        counter.total_out += quantita
        session.commit()
    except Exception as e:
        logging.error(f"Errore aggiornamento total_out: {e}")
        session.rollback()
    finally:
        session.close()
    return True

def verifica_transazione_gky(user_address, tx_hash, cost):
    try:
        tx = w3.eth.get_transaction(tx_hash)
        if tx["to"].lower() != CONTRATTO_GKY.lower():
            logging.error("TX non destinata al contratto GKY.")
            return False
        contract = w3.eth.contract(address=CONTRATTO_GKY, abi=[{
            "constant": False,
            "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}],
            "name": "transfer",
            "outputs": [{"name": "", "type": "bool"}],
            "payable": False,
            "stateMutability": "nonpayable",
            "type": "function",
        }])
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
    r = random.random() * 100
    if r < 0.02:
        return "NFT BASISC"
    elif r < 0.06:
        return "NFT STARTER"
    else:
        r2 = r - 0.06
        if r2 < 30:
            return "NO PRIZE"
        elif r2 < 30 + 25:
            return "10 GKY"
        elif r2 < 55 + 20:
            return "20 GKY"
        elif r2 < 75 + 10:
            return "50 GKY"
        elif r2 < 85 + 7:
            return "100 GKY"
        elif r2 < 92 + 4:
            return "250 GKY"
        elif r2 < 96 + 2:
            return "500 GKY"
        else:
            return "1000 GKY"

#######################################
# COMANDI DEL BOT ESISTENTI
#######################################

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0].startswith("ref_"):
        inviter_id = context.args[0].split("_")[1]
        telegram_id = str(update.message.from_user.id)
        session = Session()
        try:
            user = session.query(User).filter_by(telegram_id=telegram_id).first()
            if not user:
                user = User(telegram_id=telegram_id, extra_spins=0, referred_by=inviter_id)
                session.add(user)
                session.commit()
                inviter = session.query(User).filter_by(telegram_id=inviter_id).first()
                if inviter:
                    inviter.extra_spins += 2
                    session.commit()
                    await update.message.reply_text(f"✅ Registrazione tramite referral completata! L'utente {inviter_id} ha guadagnato 2 extra tiri.")
            else:
                if not user.referred_by:
                    user.referred_by = inviter_id
                    session.commit()
                    inviter = session.query(User).filter_by(telegram_id=inviter_id).first()
                    if inviter:
                        inviter.extra_spins += 2
                        session.commit()
                        await update.message.reply_text(f"✅ Referral registrato! L'utente {inviter_id} ha guadagnato 2 extra tiri.")
        except Exception as e:
            logging.error(f"Errore in referral in start: {e}")
            session.rollback()
        finally:
            session.close()
    await update.message.reply_text(
        "🎉 Benvenuto in Gianky Coin!\n\n"
        "Usa /connect <wallet_address> per collegare il wallet,\n"
        "usa /ruota per visualizzare la ruota e il contatore dei tiri disponibili,\n"
        "/buyspins per acquistare extra tiri,\n"
        "/sharetask per completare la task di condivisione e guadagnare 1 giro extra (1 volta a settimana),\n"
        "oppure /referral per ottenere il tuo link referral."
    )

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.message.from_user.id)
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{telegram_id}"
    await update.message.reply_text(f"💡 Il tuo link referral:\n{link}")

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.message.from_user.id)
    if context.args and not context.args[0].startswith("ref_"):
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
        await update.message.reply_photo(photo=photo, caption=caption, reply_markup=reply_markup)
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
            f"✅ Per acquistare {num_spins} tiri extra, trasferisci {cost} GKY al portafoglio:\n**{WALLET_DISTRIBUZIONE}**\nUsa /confirmbuy <tx_hash> [<num>]"
        )
    except Exception as e:
        logging.error(f"Errore in buyspins: {e}")
        await update.message.reply_text("❌ Errore durante l'acquisto dei tiri extra.")
    finally:
        session.close()

async def confirmbuy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /confirmbuy <tx_hash> [<num>]

    Questa funzione conferma automaticamente l'acquisto di extra spin.
    Se viene fornito solo il tx_hash, il sistema decodifica l'importo trasferito:
      - 50 GKY  → 1 spin
      - 125 GKY → 3 spin
    Se l'importo non viene riconosciuto, l'utente può specificare manualmente il numero di spin extra.
    """
    telegram_id = str(update.message.from_user.id)
    session = Session()
    try:
        if not context.args or len(context.args) < 1:
            await update.message.reply_text("❌ Usa: /confirmbuy <tx_hash> [<num>]")
            return
        tx_hash = context.args[0]
        if tx_hash in USED_TX:
            await update.message.reply_text("❌ Questa transazione è già stata usata per l'acquisto di extra tiri.")
            return
        if len(context.args) == 1:
            try:
                tx = w3.eth.get_transaction(tx_hash)
                contract = w3.eth.contract(address=CONTRATTO_GKY, abi=[{
                    "constant": False,
                    "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}],
                    "name": "transfer",
                    "outputs": [{"name": "", "type": "bool"}],
                    "payable": False,
                    "stateMutability": "nonpayable",
                    "type": "function",
                }])
                func_obj, params = contract.decode_function_input(tx.input)
                token_amount = params.get("_value", 0)
                value_gky = float(w3.from_wei(token_amount, "ether"))
            except Exception as e:
                logging.error(f"Errore nella decodifica automatica: {e}")
                await update.message.reply_text("❌ Errore nella decodifica automatica. Specifica manualmente il numero di tiri extra.")
                return
            if value_gky == 50:
                num_spins = 1
            elif value_gky == 125:
                num_spins = 3
            else:
                await update.message.reply_text("❌ Importo non riconosciuto per conferma automatica. Specifica manualmente il numero di tiri extra.")
                return
        else:
            try:
                num_spins = int(context.args[1])
            except:
                await update.message.reply_text("❌ Numero di tiri deve essere un intero.")
                return
            if num_spins not in [1, 3]:
                await update.message.reply_text("❌ Solo 1 o 3 tiri extra sono ammessi.")
                return

        cost = 50 if num_spins == 1 else 125
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if not user or not user.wallet_address:
            await update.message.reply_text("⚠️ Collega il wallet con /connect")
            return
        if verifica_transazione_gky(user.wallet_address, tx_hash, cost):
            user.extra_spins = (user.extra_spins or 0) + num_spins
            session.commit()
            USED_TX.add(tx_hash)
            # Aggiorna il contatore globale per entrate
            counter = session.query(GlobalCounter).first()
            counter.total_in += cost
            session.commit()
            await update.message.reply_text(f"✅ Acquisto confermato! Extra tiri disponibili: {user.extra_spins}")
        else:
            await update.message.reply_text("❌ Transazione non valida o importo insufficiente.")
    except Exception as e:
        logging.error(f"Errore in confirmbuy: {e}")
        await update.message.reply_text("❌ Errore durante la conferma degli extra tiri.")
    finally:
        session.close()

async def sharetask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video_url = "https://www.youtube.com/watch?v=AbpPYERGCXI&ab_channel=GKY-OFFICIAL"
    keyboard = [[InlineKeyboardButton("Condividi e vinci", url=video_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "📢 Condividi questo video per vincere 1 giro extra.\n(La task può essere completata 1 volta a settimana.)",
        reply_markup=reply_markup
    )
    confirm_keyboard = [[InlineKeyboardButton("Conferma task", callback_data="confirm_share_task")]]
    confirm_markup = InlineKeyboardMarkup(confirm_keyboard)
    await update.message.reply_text("Quando hai condiviso, premi il pulsante:", reply_markup=confirm_markup)

async def confirm_share_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("⏳ Attendi, il check della task durerà max 10 minuti...")
    asyncio.create_task(delayed_reward(query))

async def delayed_reward(query):
    await asyncio.sleep(600)
    reward_keyboard = [[InlineKeyboardButton("Prendi premio", callback_data="claim_share_reward")]]
    reward_markup = InlineKeyboardMarkup(reward_keyboard)
    try:
        await query.message.reply_text("✅ Check completato. Premi 'Prendi premio' per ottenere 1 giro extra.", reply_markup=reward_markup)
    except Exception as e:
        logging.error(f"Errore in delayed_reward: {e}")

async def claim_share_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    telegram_id = str(query.from_user.id)
    session = Session()
    try:
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if not user:
            await query.edit_message_caption("⚠️ Utente non trovato. Usa /connect per collegare il wallet.")
            return
        now = datetime.datetime.now(pytz.timezone("Europe/Rome"))
        if user.last_share_task is not None:
            diff = now - user.last_share_task.astimezone(pytz.timezone("Europe/Rome"))
            if diff < datetime.timedelta(days=7):
                remaining = datetime.timedelta(days=7) - diff
                await query.edit_message_caption(f"⏳ Hai già completato la task. Rifalla per guadagnare un nuovo giro extra.\nRiprova tra {remaining}.")
                return
        user.extra_spins += 1
        user.last_share_task = now
        session.commit()
        await query.edit_message_caption(f"🎉 Task completata! Hai guadagnato 1 giro extra.\nExtra tiri disponibili: {user.extra_spins}")
    except Exception as e:
        logging.error(f"Errore in claim_share_reward: {e}")
        await query.edit_message_caption("❌ Errore durante il riscatto del premio.")
    finally:
        session.close()

async def giankyadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = Session()
    try:
        from sqlalchemy import func
        counter = session.query(GlobalCounter).first()
        total_in = counter.total_in
        total_out = counter.total_out
        report_text = (
            f"📊 Report Globali GKY:\n"
            f"Entrate totali: {total_in} GKY\n"
            f"Uscite totali: {total_out} GKY\n"
            f"Bilancio: {total_in - total_out} GKY"
        )
        await update.message.reply_text(report_text)
    except Exception as e:
        logging.error(f"Errore nel report admin: {e}")
        await update.message.reply_text("❌ Errore durante la generazione del report.")
    finally:
        session.close()

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

        italy_tz = pytz.timezone("Europe/Rome")
        now_italy = datetime.datetime.now(italy_tz)
        if user.last_play_date is None or user.last_play_date.astimezone(italy_tz).date() != now_italy.date():
            available = 1 + (user.extra_spins or 0)
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
            premio_record = PremioVinto(telegram_id=telegram_id, wallet=user.wallet_address, premio=prize, user_id=user.id)
            session.add(premio_record)
            session.commit()

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
# TASK AUTOMATICO PER VERIFICARE LE TRANSAZIONI EXTRA
#######################################

LAST_BLOCK = None

async def auto_confirm_extra_spins(context: ContextTypes.DEFAULT_TYPE):
    """
    Task automatico che, ad intervalli regolari, controlla i nuovi blocchi.
    Per ogni transazione in cui il destinatario è il CONTRATTO_GKY e il mittente corrisponde
    a un wallet registrato, decodifica l'importo trasferito.
    Se l'importo corrisponde a 50 GKY, accredita 1 spin; se 125 GKY, accredita 3 spin.
    Aggiorna anche il contatore globale (total_in).
    """
    global LAST_BLOCK
    try:
        latest_block = w3.eth.block_number
        if LAST_BLOCK is None:
            LAST_BLOCK = latest_block
            return
        for blk_num in range(LAST_BLOCK + 1, latest_block + 1):
            block = w3.eth.get_block(blk_num, full_transactions=True)
            for tx in block.transactions:
                if tx.to and tx.to.lower() == CONTRATTO_GKY.lower():
                    sender = tx["from"].lower()
                    session = Session()
                    try:
                        user = session.query(User).filter(User.wallet_address.ilike(f"{sender}%")).first()
                        if user and tx.hash.hex() not in USED_TX:
                            contract = w3.eth.contract(address=CONTRATTO_GKY, abi=[{
                                "constant": False,
                                "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}],
                                "name": "transfer",
                                "outputs": [{"name": "", "type": "bool"}],
                                "payable": False,
                                "stateMutability": "nonpayable",
                                "type": "function",
                            }])
                            try:
                                func_obj, params = contract.decode_function_input(tx.input)
                                token_amount = params.get("_value", 0)
                                value_gky = float(w3.from_wei(token_amount, "ether"))
                                spins = 0
                                if value_gky == 50:
                                    spins = 1
                                elif value_gky == 125:
                                    spins = 3
                                if spins > 0:
                                    user.extra_spins += spins
                                    USED_TX.add(tx.hash.hex())
                                    counter = session.query(GlobalCounter).first()
                                    counter.total_in += value_gky
                                    session.commit()
                                    try:
                                        await context.bot.send_message(chat_id=user.telegram_id, text=f"✅ Auto-conferma: hai ricevuto {spins} extra spin per un pagamento di {value_gky} GKY!")
                                    except Exception as msg_err:
                                        logging.error(f"Errore invio messaggio automatico: {msg_err}")
                            except Exception as decode_err:
                                logging.error(f"Errore nella decodifica automatica in blocco {blk_num}: {decode_err}")
                    finally:
                        session.close()
            LAST_BLOCK = blk_num
    except Exception as e:
        logging.error(f"Errore nel task auto_confirm_extra_spins: {e}")

#######################################
# FUNZIONE ADMIN PER REPORT GLOBALI
#######################################

async def giankyadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = Session()
    try:
        from sqlalchemy import func
        counter = session.query(GlobalCounter).first()
        total_in = counter.total_in
        total_out = counter.total_out
        report_text = (
            f"📊 Report Globali GKY:\n"
            f"Entrate totali: {total_in} GKY\n"
            f"Uscite totali: {total_out} GKY\n"
            f"Bilancio: {total_in - total_out} GKY"
        )
        await update.message.reply_text(report_text)
    except Exception as e:
        logging.error(f"Errore nel report admin: {e}")
        await update.message.reply_text("❌ Errore durante la generazione del report.")
    finally:
        session.close()

#######################################
# FUNZIONE PRINCIPALE
#######################################

def main():
    request = HTTPXRequest(connect_timeout=30, read_timeout=30)
    app = ApplicationBuilder().token(TOKEN).request(request).build()
    
    # Aggiungi gli handler dei comandi
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("connect", connect))
    app.add_handler(CommandHandler("ruota", ruota))
    app.add_handler(CommandHandler("buyspins", buyspins))
    app.add_handler(CommandHandler("confirmbuy", confirmbuy))
    app.add_handler(CommandHandler("referral", referral))
    app.add_handler(CommandHandler("sharetask", sharetask))
    app.add_handler(CommandHandler("giankyadmin", giankyadmin))
    
    # Aggiungi gli handler per le callback
    app.add_handler(CallbackQueryHandler(confirm_share_task, pattern="^confirm_share_task$"))
    app.add_handler(CallbackQueryHandler(claim_share_reward, pattern="^claim_share_reward$"))
    app.add_handler(CallbackQueryHandler(button))
    
    # Avvia il task automatico per controllare le transazioni ogni 30 secondi
    if app.job_queue:
        app.job_queue.run_repeating(auto_confirm_extra_spins, interval=30, first=10)
    else:
        logging.error("JobQueue non disponibile!")
    
    logging.info("✅ Bot in esecuzione...")
    app.run_polling()

if __name__ == '__main__':
    main()
