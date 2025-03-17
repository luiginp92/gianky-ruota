#!/usr/bin/env python3
"""
Gianky Coin Web App – main.py
-----------------------------
Gestisce:
 • Lo spin della ruota, la scelta del premio e il trasferimento automatico dei token
 • L'acquisto e la conferma degli extra giri
 • L'endpoint per il saldo del wallet
"""

import os, random, datetime, pytz, logging
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn

from web3 import Web3
from eth_account.messages import encode_defunct
from jose import JWTError, jwt

from database import Session, User, PremioVinto, GlobalCounter, init_db
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
init_db()

app = FastAPI(title="Gianky Coin Web App API")
app.mount("/static", StaticFiles(directory="static"), name="static")

# ------------------ CONFIGURAZIONE BLOCKCHAIN ------------------
PRIVATE_KEY = os.getenv("DISTRIBUTION_PRIVATE_KEY")
if not PRIVATE_KEY:
    raise RuntimeError("Errore: DISTRIBUTION_PRIVATE_KEY non impostata.")

PROVIDER_URL = os.getenv("PROVIDER_URL", "https://polygon-rpc.com/")
TOKEN_ADDRESS = os.getenv("TOKEN_ADDRESS")
if not TOKEN_ADDRESS:
    raise RuntimeError("Errore: TOKEN_ADDRESS non impostato.")

WALLET_DISTRIBUZIONE = os.getenv("WALLET_DISTRIBUZIONE", "0xBc0c054066966a7A6C875981a18376e2296e5815")

w3 = Web3(Web3.HTTPProvider(PROVIDER_URL))
w3_no_mw = Web3(Web3.HTTPProvider(PROVIDER_URL))
USED_TX = set()

# ------------------ FUNZIONI HELPER ------------------
def to_wei(val, unit):
    return Web3.to_wei(val, unit)

def from_wei(val, unit):
    return Web3.from_wei(val, unit)

def get_dynamic_gas_price():
    try:
        try:
            base = w3.eth.gas_price
        except AttributeError:
            base = w3.eth.get_gas_price()
        safe = int(base * 1.2)
        logging.info(f"Gas Price: {from_wei(base, 'gwei')} -> {from_wei(safe, 'gwei')}")
        return safe
    except Exception as e:
        logging.error(f"Errore nel gas price: {e}")
        return to_wei(50, 'gwei')

# ------------------ VERIFICA TX ------------------
def verifica_transazione_gky(user_address: str, tx_hash: str, cost: int) -> bool:
    try:
        tx = w3_no_mw.eth.get_transaction(tx_hash)
        if tx.get("to", "").lower() != TOKEN_ADDRESS.lower():
            logging.error("La TX non è indirizzata al contratto token.")
            return False
        return True
    except Exception as e:
        logging.error(f"Errore verifica TX: {e}")
        return False

# ------------------ JWT ------------------
SECRET_KEY = os.getenv("SECRET_KEY", "supersecret_jwt_key_change_me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None):
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + (expires_delta or datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# ------------------ MODELLI DI INPUT ------------------
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

# ------------------ ENDPOINT PER IL SALDO ------------------
@app.get("/api/balance/{wallet_address}")
async def get_balance(wallet_address: str):
    try:
        provider = Web3(Web3.HTTPProvider(PROVIDER_URL))
        matic_balance = provider.eth.get_balance(wallet_address)
        token_contract = provider.eth.contract(
            address=TOKEN_ADDRESS,
            abi=[{
                "constant": True,
                "inputs": [{"name": "owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "", "type": "uint256"}],
                "payable": False,
                "stateMutability": "view",
                "type": "function"
            }]
        )
        token_balance = token_contract.functions.balanceOf(wallet_address).call()
        return {"matic": float(from_wei(matic_balance, 'ether')), "gky": float(from_wei(token_balance, 'ether'))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ------------------ INVIO TOKEN ------------------
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
        nonce = w3.eth.get_transaction_count(WALLET_DISTRIBUZIONE)
        tx = token_contract.functions.transfer(destinatario, quantita * 10**18).build_transaction({
            'from': WALLET_DISTRIBUZIONE,
            'nonce': nonce,
            'gas': 100000,
            'gasPrice': gas_price,
        })
        signed_tx = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
        raw_tx = signed_tx.raw_transaction if hasattr(signed_tx, 'raw_transaction') else signed_tx.rawTransaction
        tx_hash = w3.eth.send_raw_transaction(raw_tx)
        logging.info(f"Token inviati: {quantita} GKY, txHash: {tx_hash.hex()}")
    except Exception as e:
        logging.error(f"Errore nell'invio dei token: {e}")
        return False
    session_db = Session()
    try:
        counter = session_db.query(GlobalCounter).first()
        if counter is None:
            counter = GlobalCounter(total_in=0.0, total_out=quantita)
            session_db.add(counter)
        else:
            counter.total_out += quantita
        session_db.commit()
    except Exception as e:
        logging.error(f"Errore aggiornamento total_out: {e}")
        session_db.rollback()
    finally:
        session_db.close()
    return True

# ------------------ ASSEGNAZIONE PREMIO (DISTRIBUZIONE PESATA) ------------------
def get_prize() -> str:
    # Premi e percentuali (per premi superiori a 50 GKY le percentuali sono dimezzate)
    prizes = [
        ("10 GKY", 30),
        ("20 GKY", 15),
        ("50 GKY", 10),
        ("100 GKY", 3),    # dimezzato da 5
        ("250 GKY", 1),    # dimezzato da 3
        ("500 GKY", 1),    # dimezzato da 2
        ("1000 GKY", 1),   # minimo 1
        ("NO PRIZE", 44)
    ]
    total = sum(weight for _, weight in prizes)
    r = random.uniform(0, total)
    upto = 0
    for prize, weight in prizes:
        if upto + weight >= r:
            logging.info(f"get_prize() scelto: {prize}")
            return prize
        upto += weight
    logging.info("get_prize() scelto: NO PRIZE")
    return "NO PRIZE"

# ------------------ OTTENIMENTO UTENTE ------------------
def get_user(wallet_address: str):
    session = Session()
    try:
        user = session.query(User).filter(User.wallet_address.ilike(wallet_address)).first()
        if not user:
            # Alla prima connessione, l'utente riceve anche il free spin
            user = User(wallet_address=wallet_address, extra_spins=0, last_play_date=None)
            session.add(user)
            session.commit()
            session.refresh(user)
        logging.info(f"Utente: {user.wallet_address}, extra_spins: {user.extra_spins}, last_play_date: {user.last_play_date}")
        return user
    finally:
        session.close()

# ------------------ ENDPOINT SPIN ------------------
@app.post("/api/spin")
async def api_spin(req: SpinRequest):
    user = get_user(req.wallet_address)
    session = Session()
    try:
        user = session.merge(user)
        italy = pytz.timezone("Europe/Rome")
        now = datetime.datetime.now(italy)
        # Determina se è disponibile il free spin: se l'utente non ha giocato oggi
        free_spin_available = (user.last_play_date is None or user.last_play_date.date() < now.date())
        if free_spin_available:
            # Se è disponibile il free spin, il conteggio disponibile è extra_spins + 1
            available = user.extra_spins + 1
            # Usa il free spin e aggiorna last_play_date
            user.last_play_date = now
            session.commit()
            used_spin_type = "free"
        else:
            if user.extra_spins <= 0:
                raise HTTPException(status_code=400, detail="Hai esaurito i tiri disponibili per oggi.")
            user.extra_spins -= 1
            session.commit()
            available = user.extra_spins
            used_spin_type = "extra"
        premio = get_prize()
        if premio.strip().upper() == "NO PRIZE":
            result_text = "Nessun premio vinto. Riprova!"
        elif "GKY" in premio:
            amount = int(premio.split(" ")[0])
            if invia_token(req.wallet_address, amount):
                result_text = f"Hai vinto {premio}! (spin usato: {used_spin_type})"
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
        return {"message": result_text, "prize": premio, "available_spins": available}
    except Exception as e:
        logging.error(f"Errore nello spin: {e}")
        raise HTTPException(status_code=500, detail="Errore durante lo spin.")
    finally:
        session.close()

# ------------------ ENDPOINT BUY SPINS ------------------
@app.post("/api/buyspins")
async def api_buyspins(req: BuySpinsRequest):
    user = get_user(req.wallet_address)
    try:
        if req.num_spins not in (1, 3, 10):
            raise HTTPException(status_code=400, detail="Puoi acquistare solo 1, 3 o 10 giri extra.")
        cost = 50 if req.num_spins == 1 else 125 if req.num_spins == 3 else 300
        msg = f"Per acquistare {req.num_spins} giri extra, trasferisci {cost} GKY a {WALLET_DISTRIBUZIONE} e poi conferma tramite /api/confirmbuy."
        logging.info(f"Richiesta buyspins per {req.wallet_address} con num_spins: {req.num_spins}")
        return {"message": msg}
    except Exception as e:
        logging.error(f"Errore in buyspins: {e}")
        raise HTTPException(status_code=500, detail="Errore nella richiesta d'acquisto.")

# ------------------ ENDPOINT CONFIRM BUY ------------------
@app.post("/api/confirmbuy")
async def api_confirmbuy(req: ConfirmBuyRequest):
    user = get_user(req.wallet_address)
    session = Session()
    try:
        if req.tx_hash in USED_TX:
            raise HTTPException(status_code=400, detail="Tx già usata per un acquisto.")
        if req.num_spins not in (1, 3, 10):
            raise HTTPException(status_code=400, detail="Puoi confermare solo 1, 3 o 10 giri extra.")
        cost = 50 if req.num_spins == 1 else 125 if req.num_spins == 3 else 300
        if not user.wallet_address:
            raise HTTPException(status_code=400, detail="Collega il wallet prima di confermare.")
        if not verifica_transazione_gky(user.wallet_address, req.tx_hash, cost):
            raise HTTPException(status_code=400, detail="Tx non valida o importo insufficiente.")
        USED_TX.add(req.tx_hash)
        user = session.merge(user)
        user.extra_spins += req.num_spins
        # Non resettiamo last_play_date per mantenere il free spin concesso solo una volta al giorno
        session.commit()
        session.refresh(user)
        logging.info(f"Extra spins aggiornati per {req.wallet_address}: {user.extra_spins}")
        # Aggiorna il GlobalCounter per le entrate
        session_gc = Session()
        try:
            counter = session_gc.query(GlobalCounter).first()
            if counter is None:
                counter = GlobalCounter(total_in=cost, total_out=0.0)
                session_gc.add(counter)
            else:
                counter.total_in += cost
            session_gc.commit()
        except Exception as gc_e:
            logging.error(f"Errore aggiornamento total_in: {gc_e}")
            session_gc.rollback()
        finally:
            session_gc.close()
        available = user.extra_spins
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

# ------------------ ENDPOINT DISTRIBUTE ------------------
@app.post("/api/distribute")
async def api_distribute(req: DistributePrizeRequest):
    if req.prize.strip().upper() == "NO PRIZE":
        return {"message": "Nessun premio da distribuire."}
    else:
        return {"message": f"Premio {req.prize} già distribuito al wallet {req.wallet_address}."}

# ------------------ ENDPOINT REFERRAL ------------------
@app.get("/api/referral")
async def api_referral(wallet_address: str):
    referral_link = f"https://t.me/giankytestbot?start=ref_{wallet_address}"
    return {"referral_link": referral_link}

# ------------------ ROOT ------------------
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
