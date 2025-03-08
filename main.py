#!/usr/bin/env python3
"""
Gianky Coin Web App – main.py
-----------------------------
Gestisce:
 • /api/spin: Esegue lo spin, aggiorna il contatore dei giri e determina il premio.
   Se il premio contiene "GKY", invia automaticamente i token dal wallet di distribuzione al wallet dell’utente.
 • /api/distribute: Trasferisce il premio (in GKY) dal wallet di distribuzione al wallet dell’utente.
 • /api/buyspins e /api/confirmbuy: Gestiscono l’acquisto di extra giri (senza autenticazione JWT in questo prototipo).
 • Altri endpoint (auth, referral, ecc.)
Assicurati di impostare le variabili d’ambiente richieste.
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

from jose import JWTError, jwt
# Per semplificare, in questo prototipo non usiamo le dipendenze di autenticazione nei metodi spin/acquisto

from database import Session, User, PremioVinto, GlobalCounter, init_db
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
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
# Middleware per POA (se necessario)
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

# Helper per conversione in wei (assumiamo 18 decimali per GKY)
def to_wei(amount: float, unit: str) -> int:
    if unit == 'ether':
        return int(amount * 10**18)
    return int(amount)

# ----------------- JWT & AUTENTICAZIONE (per auth) -----------------
SECRET_KEY = os.getenv("SECRET_KEY", "supersecret_jwt_key_change_me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None):
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + (expires_delta or datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# ----------------- MODELLI DI INPUT -----------------
class SpinRequest(BaseModel):
    wallet_address: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")

class BuySpinsRequest(BaseModel):
    wallet_address: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")
    num_spins: int = Field(..., description="Numero di extra spin (1, 3 o 10)", gt=0)

class ConfirmBuyRequest(BaseModel):
    wallet_address: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")
    tx_hash: str
    num_spins: int = Field(..., description="Numero di extra tiri (1, 3 o 10)", gt=0)

class DistributePrizeRequest(BaseModel):
    wallet_address: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")
    prize: str

class AuthRequest(BaseModel):
    wallet_address: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")
    telegram_id: Optional[str] = None

class AuthVerifyRequest(BaseModel):
    wallet_address: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")
    signature: str

# ----------------- FUNZIONI UTILI -----------------
def get_dynamic_gas_price():
    try:
        base = w3.eth.gasPrice  # proprietà della versione 5
        safe = int(base * 1.2)
        logging.info(f"Gas Price: {w3.fromWei(base, 'gwei')} -> {w3.fromWei(safe, 'gwei')}")
        return safe
    except Exception as e:
        logging.error(f"Errore nel gas price: {e}")
        return Web3.toWei(50, 'gwei')

def invia_token(destinatario: str, quantita: int) -> bool:
    try:
        gas_price = get_dynamic_gas_price()
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
        nonce = w3.eth.getTransactionCount(WALLET_DISTRIBUZIONE)
        tx = token_contract.functions.transfer(
            destinatario,
            quantita * 10**18
        ).build_transaction({
            'from': WALLET_DISTRIBUZIONE,
            'nonce': nonce,
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
    # Per semplicità, scegliamo casualmente tra alcuni premi (modifica come preferisci)
    prizes = ['10 GKY', '10 GKY', '20 GKY', '50 GKY', '100 GKY', '250 GKY', '500 GKY', '1000 GKY', 'NO PRIZE', 'NO PRIZE', 'NO PRIZE']
    return random.choice(prizes)

def get_user(wallet_address: str):
    session = Session()
    try:
        user = session.query(User).filter(User.wallet_address.ilike(wallet_address)).first()
        if not user:
            user = User(wallet_address=wallet_address, extra_spins=0)
            session.add(user)
            session.commit()
            session.refresh(user)
        logging.info(f"Utente: {user.wallet_address}, extra_spins: {user.extra_spins}")
        return user
    finally:
        session.close()

# ----------------- ENDPOINTS -----------------
# Gli endpoint di spin, buyspins e confirmbuy ora usano il wallet fornito nel body (senza dipendenza JWT)

@app.post("/api/spin")
async def api_spin(req: SpinRequest):
    user = get_user(req.wallet_address)
    session = Session()
    try:
        italy = pytz.timezone("Europe/Rome")
        now = datetime.datetime.now(italy)
        # Se è il primo spin del giorno, l'utente ha 1 giro base + extra
        if not user.last_play_date or user.last_play_date.astimezone(italy).date() != now.date():
            available = 1 + user.extra_spins
            user.last_play_date = now
            session.commit()
        else:
            available = user.extra_spins or 0
            if available <= 0:
                raise HTTPException(status_code=400, detail="Hai esaurito i tiri disponibili per oggi.")
        premio = get_prize()
        if premio == "NO PRIZE":
            result_text = "Nessun premio vinto. Riprova!"
        elif "GKY" in premio:
            amount = int(premio.split(" ")[0])
            if invia_token(req.wallet_address, amount):
                result_text = f"Hai vinto {premio}!"
            else:
                result_text = "Errore nel trasferimento dei token."
        else:
            result_text = f"Hai vinto: {premio}!"
            record = PremioVinto(
                telegram_id=user.telegram_id or "N/A",
                wallet=user.wallet_address,
                premio=premio,
                user_id=user.id
            )
            session.add(record)
            session.commit()
        logging.info(f"Spin per {req.wallet_address}: premio {premio}")
        return {"message": result_text, "prize": premio, "available_spins": 1 + user.extra_spins}
    except Exception as e:
        logging.error(f"Errore nello spin: {e}")
        raise HTTPException(status_code=500, detail="Errore durante lo spin.")
    finally:
        session.close()

@app.post("/api/distribute")
async def api_distribute(req: DistributePrizeRequest):
    user = get_user(req.wallet_address)
    if req.prize == "NO PRIZE":
        return {"message": "Nessun premio da distribuire."}
    if "GKY" in req.prize:
        try:
            amount = int(req.prize.split(" ")[0])
        except Exception:
            raise HTTPException(status_code=400, detail="Formato premio non valido.")
        if invia_token(req.wallet_address, amount):
            return {"message": f"Premio {req.prize} trasferito correttamente al wallet {req.wallet_address}."}
        else:
            raise HTTPException(status_code=500, detail="Errore nel trasferimento del premio.")
    else:
        return {"message": f"Premio {req.prize} registrato per il wallet {req.wallet_address}."}

@app.post("/api/buyspins")
async def api_buyspins(req: BuySpinsRequest):
    user = get_user(req.wallet_address)
    try:
        if req.num_spins not in (1, 3, 10):
            raise HTTPException(status_code=400, detail="Puoi acquistare solo 1, 3 o 10 giri extra.")
        cost = 50 if req.num_spins == 1 else (125 if req.num_spins == 3 else 300)
        msg = f"Per acquistare {req.num_spins} giri extra, trasferisci {cost} GKY a {WALLET_DISTRIBUZIONE} e poi conferma tramite /api/confirmbuy."
        logging.info(f"Richiesta buyspins per {req.wallet_address} con num_spins: {req.num_spins}")
        return {"message": msg}
    except Exception as e:
        logging.error(f"Errore in buyspins: {e}")
        raise HTTPException(status_code=500, detail="Errore nella richiesta d'acquisto.")

@app.post("/api/confirmbuy")
async def api_confirmbuy(req: ConfirmBuyRequest):
    user = get_user(req.wallet_address)
    session = Session()
    try:
        if req.tx_hash in USED_TX:
            raise HTTPException(status_code=400, detail="Tx già usata per un acquisto.")
        if req.num_spins not in (1, 3, 10):
            raise HTTPException(status_code=400, detail="Puoi confermare solo 1, 3 o 10 giri extra.")
        cost = 50 if req.num_spins == 1 else (125 if req.num_spins == 3 else 300)
        try:
            tx = w3_no_mw.eth.get_transaction(req.tx_hash)
        except Exception as e:
            raise HTTPException(status_code=400, detail="Tx non trovata.")
        if not tx:
            raise HTTPException(status_code=400, detail="Tx non trovata.")
        USED_TX.add(req.tx_hash)
        user.extra_spins += req.num_spins
        user.last_play_date = None
        session.commit()
        logging.info(f"Extra spins aggiornati per {req.wallet_address}: {user.extra_spins}")
        available = 1 + user.extra_spins
        return {"message": f"Acquisto confermato! Extra giri: {user.extra_spins}", "available_spins": available}
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

@app.get("/wheel")
async def get_wheel():
    # Se è presente un'immagine di fallback (non usata se si usa Winwheel.js)
    image_path = os.path.join("static", "ruota.png")
    if os.path.exists(image_path):
        return FileResponse(image_path, media_type="image/png")
    else:
        raise HTTPException(status_code=404, detail="Immagine della ruota non trovata.")

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
