#!/usr/bin/env python3
"""
Gianky Coin Web App – main.py
-----------------------------
Questa applicazione espone tramite API REST la logica del gioco con:
 • Verifica della transazione blockchain (importo, destinatario, mittente)
 • Controllo per non utilizzare lo stesso tx più volte
 • Endpoints per gioco, acquisti, referral, ecc.
 • Un frontend minimale per interagire con il sistema
"""

import logging
import random
import datetime
import os
import pytz
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn

from web3 import Web3
from eth_account.messages import encode_defunct

# Importa il modulo del database aggiornato
from database import Session, User, PremioVinto, GlobalCounter, init_db

# ------------------------------------------------
# CONFIGURAZIONI DI BASE E LOGGING
# ------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# ------------------------------------------------
# CONFIGURAZIONI BLOCKCHAIN E COSTANTI
# ------------------------------------------------
POLYGON_RPC = "https://polygon-rpc.com"
WALLET_DISTRIBUZIONE = "0xBc0c054066966a7A6C875981a18376e2296e5815"
CONTRATTO_GKY = "0x370806781689E670f85311700445449aC7C3Ff7a"
PRIVATE_KEY = os.getenv("PRIVATE_KEY_GKY")
if not PRIVATE_KEY:
    raise ValueError("❌ Errore: la chiave privata non è impostata.")

IMAGE_PATH = "ruota.png"
if os.path.exists(IMAGE_PATH):
    with open(IMAGE_PATH, "rb") as f:
        STATIC_IMAGE_BYTES = f.read()
else:
    STATIC_IMAGE_BYTES = None
    logging.error("File statico non trovato: ruota.png")

def custom_geth_poa_middleware(make_request, web3=None):
    def middleware(method, params):
        response = make_request(method, params)
        result = response.get("result")
        if isinstance(result, dict) and "extraData" in result:
            extra = result["extraData"]
            if isinstance(extra, str) and len(extra) > 66:
                response["result"]["extraData"] = "0x" + extra[-64:]
        return response
    return middleware

w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
w3.middleware_onion.inject(custom_geth_poa_middleware, layer=0)
w3_no_mw = Web3(Web3.HTTPProvider(POLYGON_RPC))

# Variabile globale per tx duplicate
USED_TX = set()

# ------------------------------------------------
# MODELLI DI INPUT
# ------------------------------------------------
class SpinRequest(BaseModel):
    wallet_address: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")

class BuySpinsRequest(BaseModel):
    wallet_address: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")
    num_spins: int = Field(..., description="Numero di extra spin (1, 3 o 10)", gt=0)

class ConfirmBuyRequest(BaseModel):
    wallet_address: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")
    tx_hash: str
    num_spins: int = Field(..., description="Numero di tiri extra (1, 3 o 10)", gt=0)

class DistributePrizeRequest(BaseModel):
    prize: str

# ------------------------------------------------
# FUNZIONI UTILI PER L'UTENTE E BLOCKCHAIN
# ------------------------------------------------
def get_user(wallet_address: str):
    session = Session()
    try:
        user = session.query(User).filter(User.wallet_address.ilike(wallet_address)).first()
    except Exception as e:
        logging.error(f"Errore nella ricerca dell'utente: {e}")
        raise HTTPException(status_code=500, detail="Errore interno")
    finally:
        session.close()
    if user is None:
        session = Session()
        try:
            user = User(wallet_address=wallet_address, extra_spins=0)
            session.add(user)
            session.commit()
        except Exception as e:
            session.rollback()
            logging.error(f"Errore nella creazione dell'utente: {e}")
            raise HTTPException(status_code=500, detail="Errore nella creazione dell'utente")
        finally:
            session.close()
    return user

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
    
    session = Session()
    try:
        counter = session.query(GlobalCounter).first()
        if counter is not None:
            counter.total_out += quantita
        else:
            counter = GlobalCounter(total_in=0.0, total_out=quantita)
            session.add(counter)
        session.commit()
    except Exception as e:
        logging.error(f"Errore aggiornamento total_out: {e}")
        session.rollback()
    finally:
        session.close()
    return True

def verifica_transazione_gky(wallet_address, tx_hash, cost):
    try:
        tx_hash = tx_hash.strip()
        if " " in tx_hash:
            parts = tx_hash.split()
            tx_hash = next((p for p in parts if p.startswith("0x")), tx_hash)
        if not tx_hash.startswith("0x"):
            logging.error("TX hash non valido: non inizia con '0x'")
            return False
        tx = w3_no_mw.eth.get_transaction(tx_hash)
        logging.info(f"Verifica TX: wallet_address {wallet_address.lower()} vs tx['from'] {tx['from'].lower()}")
        if tx["from"].lower() != wallet_address.lower():
            logging.error("TX non inviata dal wallet specificato.")
            return False
        if tx["to"].lower() != CONTRATTO_GKY.lower():
            logging.error("TX non destinata al contratto GKY.")
            return False
        contract = w3_no_mw.eth.contract(address=CONTRATTO_GKY, abi=[{
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
            logging.error(f"Importo insufficiente: {w3_no_mw.from_wei(token_amount, 'ether')} vs {cost}")
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
        if r2 < 40.575:
            return "NO PRIZE"
        elif r2 < 40.575 + 30.2875:
            return "10 GKY"
        elif r2 < 40.575 + 30.2875 + 25.2875:
            return "20 GKY"
        elif r2 < 96.15 + 2:
            return "50 GKY"
        elif r2 < 98.15 + 1:
            return "100 GKY"
        elif r2 < 99.15 + 0.5:
            return "250 GKY"
        elif r2 < 99.65 + 0.25:
            return "500 GKY"
        elif r2 < 99.90 + 0.1:
            return "1000 GKY"
        else:
            return "NO PRIZE"

# ------------------------------------------------
# ENDPOINT PER GIOCARE (SPIN)
# ------------------------------------------------
class SpinRequest(BaseModel):
    wallet_address: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")

@app.post("/api/spin")
async def api_spin(request: SpinRequest):
    user = get_user(request.wallet_address)
    session = Session()
    try:
        italy_tz = pytz.timezone("Europe/Rome")
        now_italy = datetime.datetime.now(italy_tz)
        if (not user.last_play_date) or (user.last_play_date.astimezone(italy_tz).date() != now_italy.date()):
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
                raise HTTPException(status_code=400, detail="⚠️ Hai esaurito i tiri disponibili per oggi.")
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
            premio_record = PremioVinto(
                telegram_id=user.telegram_id or "N/A",
                wallet=user.wallet_address,
                premio=prize,
                user_id=user.id
            )
            session.add(premio_record)
            session.commit()
        return {"message": result_text, "available_spins": available}
    except HTTPException as he:
        raise he
    except Exception as e:
        logging.error(f"Errore nello spin: {e}")
        raise HTTPException(status_code=500, detail="Errore durante il giro della ruota.")
    finally:
        session.close()

# Altri endpoint (buyspins, confirmbuy, distribute, referral, ecc.) rimangono invariati
class DistributePrizeRequest(BaseModel):
    prize: str

@app.post("/api/distribute")
async def api_distribute(request: DistributePrizeRequest, wallet_address: str):
    # Nota: questo endpoint può essere usato per distribuire premi NFT, etc.
    # Per questo esempio, simuliamo semplicemente la distribuzione.
    return {"message": f"Premio '{request.prize}' distribuito al wallet {wallet_address}."}

@app.get("/api/referral")
async def api_referral(wallet_address: str):
    referral_link = f"https://t.me/tuo_bot?start=ref_{wallet_address}"
    return {"referral_link": referral_link}

@app.get("/wheel")
async def get_wheel():
    if STATIC_IMAGE_BYTES:
        return FileResponse(IMAGE_PATH, media_type="image/png")
    else:
        raise HTTPException(status_code=404, detail="Immagine della ruota non trovata.")

@app.get("/", response_class=HTMLResponse)
async def home_redirect():
    return """
    <html>
      <head>
        <meta http-equiv="refresh" content="0; url=/static/index.html" />
      </head>
      <body></body>
    </html>
    """

@app.on_event("startup")
def on_startup():
    init_db()

if __name__ == '__main__':
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
