#!/usr/bin/env python3
"""
Gianky Coin Web App – main.py
-----------------------------
Questo modulo gestisce:
 • Logica del gioco: spin della ruota, distribuzione automatica dei premi e acquisto extra tiri.
 • Endpoint per referral, share task, report admin.
 
I parametri per le transazioni (chiave privata, provider URL, indirizzo token e wallet di distribuzione)
sono letti dalle variabili d’ambiente (es. in un file .env).
"""

import os
import random
import datetime
import pytz
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn

from web3 import Web3
from eth_account.messages import encode_defunct

from database import Session, User, PremioVinto, GlobalCounter, init_db

# Carica le variabili d’ambiente
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# Inizializza il database
init_db()

app = FastAPI(title="Gianky Coin Web App API")
app.mount("/static", StaticFiles(directory="static"), name="static")

# ----------------- CONFIGURAZIONE BLOCKCHAIN -----------------
PRIVATE_KEY = os.getenv("DISTRIBUTION_PRIVATE_KEY")
if not PRIVATE_KEY:
    raise RuntimeError("Errore: DISTRIBUTION_PRIVATE_KEY non impostata.")

PROVIDER_URL = os.getenv("PROVIDER_URL", "https://polygon-rpc.com/")
TOKEN_ADDRESS = os.getenv("TOKEN_ADDRESS")
if not TOKEN_ADDRESS:
    raise RuntimeError("Errore: TOKEN_ADDRESS non impostato.")

WALLET_DISTRIBUZIONE = os.getenv("WALLET_DISTRIBUZIONE", "0xBc0c054066966a7A6C875981a18376e2296e5815")

w3 = Web3(Web3.HTTPProvider(PROVIDER_URL))
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
w3.middleware_onion.inject(custom_geth_poa_middleware, layer=0)
w3_no_mw = Web3(Web3.HTTPProvider(PROVIDER_URL))
USED_TX = set()

# ----------------- MODELLI DI INPUT -----------------
class SpinRequest(BaseModel):
    wallet_address: str = Field(..., regex="^0x[a-fA-F0-9]{40}$")

class BuySpinsRequest(BaseModel):
    walletAddress: str = Field(..., regex="^0x[a-fA-F0-9]{40}$")
    numSpins: int = Field(..., description="Numero di extra spin (1, 3 o 10)", gt=0)

class ConfirmBuyRequest(BaseModel):
    walletAddress: str = Field(..., regex="^0x[a-fA-F0-9]{40}$")
    txHash: str
    numSpins: int = Field(..., description="Numero di extra tiri (1, 3 o 10)", gt=0)

class DistributePrizeRequest(BaseModel):
    wallet_address: str = Field(..., regex="^0x[a-fA-F0-9]{40}$")
    prize: str

# ----------------- FUNZIONI UTILI -----------------
def get_user(wallet_address: str) -> User:
    session = Session()
    try:
        user = session.query(User).filter(User.wallet_address.ilike(wallet_address)).first()
    except Exception as e:
        logging.error(f"Errore nella ricerca dell'utente: {e}")
        raise HTTPException(status_code=500, detail="Errore interno")
    finally:
        session.close()
    if not user:
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
    logging.info(f"Utente: {user.wallet_address}, extra_spins: {user.extra_spins}")
    return user

def get_dynamic_gas_price():
    try:
        base = w3.eth.gasPrice
        safe = int(base * 1.2)
        logging.info(f"Gas Price: {w3.fromWei(base, 'gwei')} -> {w3.fromWei(safe, 'gwei')}")
        return safe
    except Exception as e:
        logging.error(f"Errore nel gas price: {e}")
        return Web3.toWei('50', 'gwei')

def invia_token(destinatario: str, quantita: int) -> bool:
    gas_price = get_dynamic_gas_price()
    try:
        token_contract = w3.eth.contract(
            address=TOKEN_ADDRESS,
            abi=[{
                "constant": False,
                "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}],
                "name": "transfer",
                "outputs": [{"name": "", "type": "bool"}],
                "payable": False,
                "stateMutability": "nonpayable",
                "type": "function"
            }]
        )
        tx = token_contract.functions.transfer(destinatario, quantita * 10**18).build_transaction({
            'from': WALLET_DISTRIBUZIONE,
            'nonce': w3.eth.get_transaction_count(WALLET_DISTRIBUZIONE),
            'gas': 100000,
            'gasPrice': gas_price,
        })
        signed_tx = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        logging.info(f"Token inviati: {quantita} GKY, txHash: {tx_hash.hex()}")
    except Exception as e:
        logging.error(f"Errore nell'invio dei token: {e}")
        return False
    session_db = Session()
    try:
        counter = session_db.query(GlobalCounter).first()
        if counter:
            counter.total_out += quantita
        else:
            counter = GlobalCounter(total_in=0.0, total_out=quantita)
            session_db.add(counter)
        session_db.commit()
    except Exception as e:
        logging.error(f"Errore aggiornamento total_out: {e}")
        session_db.rollback()
    finally:
        session_db.close()
    return True

def get_prize() -> str:
    // Distribuzione basata su probabilità che corrisponde ai segmenti della ruota
    r = random.random() * 100
    if r < 10:
        return "10 GKY"
    elif r < 15:
        return "20 GKY"
    elif r < 25:
        return "50 GKY"
    elif r < 35:
        return "100 GKY"
    elif r < 45:
        return "250 GKY"
    elif r < 50:
        return "500 GKY"
    elif r < 55:
        return "1000 GKY"
    elif r < 60:
        return "NFT BASISC"
    elif r < 65:
        return "NFT STARTER"
    elif r < 80:
        return "NO PRIZE"
    elif r < 90:
        return "NO PRIZE"
    else:
        return "NO PRIZE"

# ----------------- ENDPOINTS -----------------

@app.post("/api/spin")
async def api_spin(req: SpinRequest):
    current_user = get_user(req.wallet_address)
    session = Session()
    try:
        italy = pytz.timezone("Europe/Rome")
        now = datetime.datetime.now(italy)
        if not current_user.last_play_date or current_user.last_play_date.astimezone(italy).date() != now.date():
            available = 1 + (current_user.extra_spins or 0)
            current_user.last_play_date = now
            session.commit()
        else:
            available = current_user.extra_spins or 0
            if available > 0:
                current_user.extra_spins -= 1
                session.commit()
                available -= 1
            else:
                raise HTTPException(status_code=400, detail="Hai esaurito i tiri disponibili per oggi.")
        premio = get_prize()
        if premio == "NO PRIZE":
            result_text = "Nessun premio vinto. Riprova!"
        elif "GKY" in premio:
            amount = int(premio.split(" ")[0])
            if invia_token(current_user.wallet_address, amount):
                result_text = f"Hai vinto {premio}!"
            else:
                result_text = "Errore nel trasferimento dei token."
        else:
            result_text = f"Hai vinto: {premio}!"
            record = PremioVinto(
                telegram_id=current_user.telegram_id or "N/A",
                wallet=current_user.wallet_address,
                premio=premio,
                user_id=current_user.id
            )
            session.add(record)
            session.commit()
        logging.info(f"Spin per {current_user.wallet_address}: premio {premio}, giri residui {available}")
        return {"message": result_text, "available_spins": available, "prize": premio}
    except HTTPException as he:
        raise he
    except Exception as e:
        logging.error(f"Errore nello spin: {e}")
        raise HTTPException(status_code=500, detail="Errore durante il giro della ruota.")
    finally:
        session.close()

@app.post("/api/distribute")
async def api_distribute(req: DistributePrizeRequest):
    current_user = get_user(req.wallet_address)
    if "GKY" in req.prize:
        try:
            amount = int(req.prize.split(" ")[0])
        except Exception:
            raise HTTPException(status_code=400, detail="Formato premio non valido.")
        if invia_token(current_user.wallet_address, amount):
            return {"message": f"Premio '{req.prize}' trasferito correttamente al wallet {current_user.wallet_address}."}
        else:
            raise HTTPException(status_code=500, detail="Errore nel trasferimento del premio.")
    else:
        return {"message": f"Premio '{req.prize}' assegnato al wallet {current_user.wallet_address}."}

@app.post("/api/buyspins")
async def api_buyspins(req: BuySpinsRequest):
    current_user = get_user(req.walletAddress)
    session = Session()
    try:
        if req.numSpins not in (1, 3, 10):
            raise HTTPException(status_code=400, detail="Puoi acquistare solo 1, 3 o 10 giri extra.")
        cost = 50 if req.numSpins == 1 else 125 if req.numSpins == 3 else 300
        msg = f"Trasferisci {cost} GKY a {WALLET_DISTRIBUZIONE} e poi chiama /api/confirmbuy con il tx hash."
        return {"message": msg}
    except Exception as e:
        logging.error(f"Errore in buyspins: {e}")
        raise HTTPException(status_code=500, detail="Errore nella richiesta d'acquisto.")
    finally:
        session.close()

@app.post("/api/confirmbuy")
async def api_confirmbuy(req: ConfirmBuyRequest):
    current_user = get_user(req.walletAddress)
    session = Session()
    try:
        if req.txHash in USED_TX:
            raise HTTPException(status_code=400, detail="Tx già usata per un acquisto.")
        if req.numSpins not in (1, 3, 10):
            raise HTTPException(status_code=400, detail="Puoi confermare solo 1, 3 o 10 giri extra.")
        cost = 50 if req.numSpins == 1 else 125 if req.numSpins == 3 else 300
        if not verifica_transazione_gky(current_user.wallet_address, req.txHash, cost):
            raise HTTPException(status_code=400, detail="Tx non valida o importo insufficiente.")
        current_user.extra_spins = (current_user.extra_spins or 0) + req.numSpins
        current_user.last_play_date = None  # reset per consentire nuovi spin
        session.commit()
        session.refresh(current_user)
        logging.info(f"Extra spins aggiornati: {current_user.extra_spins}")
        USED_TX.add(req.txHash)
        counter = session.query(GlobalCounter).first()
        if counter:
            counter.total_in += cost
        else:
            counter = GlobalCounter(total_in=cost, total_out=0.0)
            session.add(counter)
        session.commit()
        available = 1 + (current_user.extra_spins or 0)
        return {"message": f"Acquisto confermato! Extra giri: {current_user.extra_spins}", "available_spins": available}
    except HTTPException as he:
        session.rollback()
        raise he
    except Exception as e:
        session.rollback()
        logging.error(f"Errore in confirmbuy: {e}")
        raise HTTPException(status_code=500, detail="Errore nella conferma degli extra giri.")
    finally:
        session.close()

@app.get("/api/referral")
async def api_referral(wallet_address: str):
    referral_link = f"https://t.me/tuo_bot?start=ref_{wallet_address}"
    return {"referral_link": referral_link}

@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <html>
      <head>
        <meta http-equiv="refresh" content="0; url=/static/index.html" />
      </head>
      <body></body>
    </html>
    """

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
