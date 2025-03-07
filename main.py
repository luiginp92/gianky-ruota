#!/usr/bin/env python3
"""
Gianky Coin Web App – main.py
-----------------------------
Questo modulo gestisce:
  • La logica del gioco: spin della ruota, distribuzione automatica dei premi e acquisto extra giri.
  • Altri endpoint: referral, share task, report admin.
  
I parametri per le transazioni (chiave privata, provider URL, indirizzo token e wallet di distribuzione)
sono letti dalle variabili d’ambiente.
"""

import os
import random
import datetime
import pytz
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn

from web3 import Web3
from eth_account.messages import encode_defunct

from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer

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

# ----------------- MODELLI DI INPUT (Pydantic) -----------------
class SpinRequest(BaseModel):
    wallet_address: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")

class AuthRequest(BaseModel):
    wallet_address: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")
    telegram_id: Optional[str] = None

class AuthVerifyRequest(BaseModel):
    wallet_address: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")
    signature: str

class BuySpinsRequest(BaseModel):
    wallet_address: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")
    num_spins: int = Field(..., description="Numero di extra spin (1, 3 o 10)", gt=0)

class ConfirmBuyRequest(BaseModel):
    wallet_address: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")
    txHash: str
    numSpins: int = Field(..., description="Numero di extra tiri (1, 3 o 10)", gt=0)

class DistributePrizeRequest(BaseModel):
    wallet_address: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")
    prize: str

# ----------------- JWT & AUTENTICAZIONE (non usato per gli endpoint di gioco) -----------------
SECRET_KEY = os.getenv("SECRET_KEY", "supersecret_jwt_key_change_me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None):
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + (expires_delta or datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/verify")

def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Autenticazione non valida",
        headers={"WWW-Authenticate": "Bearer"}
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        wallet_address = payload.get("wallet_address")
        if not wallet_address:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    session = Session()
    try:
        user = session.query(User).filter(User.wallet_address.ilike(wallet_address)).first()
    finally:
        session.close()
    if not user:
        raise credentials_exception
    return user

# ----------------- FUNZIONI UTILI -----------------
def get_user(wallet_address: str):
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

def verifica_transazione_gky(user_address: str, tx_hash: str, cost: int) -> bool:
    try:
        tx = w3_no_mw.eth.get_transaction(tx_hash)
    except Exception as e:
        logging.error(f"Transazione {tx_hash} non trovata: {e}")
        return False
    if tx.get("to", "").lower() != TOKEN_ADDRESS.lower():
        logging.error("La TX non è indirizzata al contratto token.")
        return False
    token_contract = w3_no_mw.eth.contract(
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
    try:
        func_obj, params = token_contract.decode_function_input(tx.input)
    except Exception as decode_error:
        logging.error(f"Decodifica fallita: {decode_error}")
        return False
    if func_obj.fn_name != "transfer":
        logging.error("La TX non richiama transfer.")
        return False
    if params.get("_to", "").lower() != WALLET_DISTRIBUZIONE.lower():
        logging.error("La TX non invia al wallet di distribuzione.")
        return False
    token_amount = params.get("_value", 0)
    if token_amount < cost * 10**18:
        logging.error(f"Importo insufficiente: {w3_no_mw.fromWei(token_amount, 'ether')} vs {cost}")
        return False
    return True

def get_prize() -> str:
    r = random.random() * 100
    # Distribuzione basata su probabilità – i segmenti della ruota sono fissi
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
    else:
        return "NO PRIZE"

# ----------------- ENDPOINTS -----------------

# Endpoint per il giro della ruota (spin)
@app.post("/api/spin")
async def api_spin(req: SpinRequest):
    user = get_user(req.wallet_address)
    session = Session()
    try:
        italy = pytz.timezone("Europe/Rome")
        now = datetime.datetime.now(italy)
        if not user.last_play_date or user.last_play_date.astimezone(italy).date() != now.date():
            available = 1 + (user.extra_spins or 0)
            user.last_play_date = now
            session.commit()
        else:
            available = user.extra_spins or 0
            if available > 0:
                user.extra_spins -= 1
                session.commit()
                available -= 1
            else:
                raise HTTPException(status_code=400, detail="Hai esaurito i tiri disponibili per oggi.")
        premio = get_prize()
        if premio == "NO PRIZE":
            result_text = "Nessun premio vinto. Riprova!"
        elif "GKY" in premio:
            amount = int(premio.split(" ")[0])
            if invia_token(user.wallet_address, amount):
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
        logging.info(f"Spin per {user.wallet_address}: premio {premio}")
        return {"message": result_text, "prize": premio}
    except HTTPException as he:
        raise he
    except Exception as e:
        logging.error(f"Errore nello spin: {e}")
        raise HTTPException(status_code=500, detail="Errore durante il giro della ruota.")
    finally:
        session.close()

# Endpoint per distribuire il premio (trasferisce i token)
@app.post("/api/distribute")
async def api_distribute(req: DistributePrizeRequest):
    user = get_user(req.wallet_address)
    if "GKY" in req.prize:
        try:
            amount = int(req.prize.split(" ")[0])
        except Exception:
            raise HTTPException(status_code=400, detail="Formato premio non valido.")
        if invia_token(user.wallet_address, amount):
            return {"message": f"Premio '{req.prize}' trasferito correttamente al wallet {user.wallet_address}."}
        else:
            raise HTTPException(status_code=500, detail="Errore nel trasferimento del premio.")
    else:
        return {"message": f"Premio '{req.prize}' assegnato al wallet {user.wallet_address}."}

# Endpoint per richiedere le istruzioni per acquistare extra giri
@app.post("/api/buyspins")
async def api_buyspins(req: BuySpinsRequest):
    user = get_user(req.wallet_address)
    session = Session()
    try:
        if req.num_spins not in (1, 3, 10):
            raise HTTPException(status_code=400, detail="Puoi acquistare solo 1, 3 o 10 giri extra.")
        cost = 50 if req.num_spins == 1 else 125 if req.num_spins == 3 else 300
        msg = f"Trasferisci {cost} GKY a {WALLET_DISTRIBUZIONE} e poi chiama /api/confirmbuy con il tx hash."
        return {"message": msg}
    except Exception as e:
        logging.error(f"Errore in buyspins: {e}")
        raise HTTPException(status_code=500, detail="Errore nella richiesta d'acquisto.")
    finally:
        session.close()

# Endpoint per confermare l'acquisto degli extra giri
@app.post("/api/confirmbuy")
async def api_confirmbuy(req: ConfirmBuyRequest):
    user = get_user(req.wallet_address)
    session = Session()
    try:
        if req.txHash in USED_TX:
            raise HTTPException(status_code=400, detail="Tx già usata per un acquisto.")
        if req.numSpins not in (1, 3, 10):
            raise HTTPException(status_code=400, detail="Puoi confermare solo 1, 3 o 10 giri extra.")
        cost = 50 if req.numSpins == 1 else 125 if req.numSpins == 3 else 300
        if not user.wallet_address:
            raise HTTPException(status_code=400, detail="Collega il wallet prima di confermare.")
        if not verifica_transazione_gky(user.wallet_address, req.txHash, cost):
            raise HTTPException(status_code=400, detail="Tx non valida o importo insufficiente.")
        user.extra_spins = (user.extra_spins or 0) + req.numSpins
        user.last_play_date = None  # Reset per consentire nuovi spin
        session.commit()
        session.refresh(user)
        logging.info(f"Extra spins aggiornati: {user.extra_spins}")
        USED_TX.add(req.txHash)
        counter = session.query(GlobalCounter).first()
        if counter:
            counter.total_in += cost
        else:
            counter = GlobalCounter(total_in=cost, total_out=0.0)
            session.add(counter)
        session.commit()
        available = 1 + (user.extra_spins or 0)
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

# Endpoint referral
@app.get("/api/referral")
async def api_referral(wallet_address: str):
    referral_link = f"https://t.me/tuo_bot?start=ref_{wallet_address}"
    return {"referral_link": referral_link}

# Endpoint per ottenere l'immagine della ruota (se presente)
@app.get("/wheel")
async def get_wheel():
    image_path = os.path.join("static", "ruota.png")
    if os.path.exists(image_path):
        return FileResponse(image_path, media_type="image/png")
    else:
        raise HTTPException(status_code=404, detail="Immagine della ruota non trovata.")

# Root che reindirizza all'index
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
