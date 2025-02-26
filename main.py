#!/usr/bin/env python3
"""
Gianky Coin Web App - main.py
-----------------------------
Ripristinato e aggiornato per compatibilità con Web3 >= 6.x:
- Usa geth_poa_middleware importato da web3.middleware
- Mantiene logica esistente (ruota, acquisti, token, ecc.)
"""

import logging
import random
import datetime
import os
import pytz
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn

from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_account.messages import encode_defunct

# Per JWT
from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer

# Importa il modulo del database
from database import Session, User, PremioVinto, GlobalCounter, init_db

logging.basicConfig(level=logging.INFO)

# ------------------------------------------------
# CONFIGURAZIONI BLOCKCHAIN E COSTANTI
# ------------------------------------------------
POLYGON_RPC = "https://polygon-rpc.com"
WALLET_DISTRIBUZIONE = "0xBc0c054066966a7A6C875981a18376e2296e5815"
CONTRATTO_GKY = "0x370806781689E670f85311700445449aC7C3Ff7a"
PRIVATE_KEY = os.getenv("PRIVATE_KEY_GKY")

if not PRIVATE_KEY:
    raise ValueError("❌ Errore: la chiave privata non è impostata.")

# Inizializza Web3 con middleware POA
w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
w3.middleware_onion.inject(geth_poa_middleware, layer=0)

# ------------------------------------------------
# CONFIGURAZIONI JWT & AUTENTICAZIONE
# ------------------------------------------------
SECRET_KEY = "a_very_secret_key_change_me"
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
         detail="Could not validate credentials",
         headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        wallet_address: str = payload.get("wallet_address")
        if wallet_address is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    session = Session()
    try:
        user = session.query(User).filter(User.wallet_address.ilike(wallet_address)).first()
    finally:
        session.close()

    if user is None:
        raise credentials_exception
    return user

# ------------------------------------------------
# FUNZIONI UTILI PER BLOCKCHAIN E GIOCO
# ------------------------------------------------
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

# ------------------------------------------------
# FUNZIONE get_prize()
# ------------------------------------------------
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
# MODELLI DI INPUT CON Pydantic
# ------------------------------------------------
class AuthRequest(BaseModel):
    wallet_address: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")
    telegram_id: Optional[str] = None

class AuthVerifyRequest(BaseModel):
    wallet_address: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")
    signature: str

class BuySpinsRequest(BaseModel):
    num_spins: int = Field(..., description="Numero di extra spin (1 o 3)", gt=0)

class ConfirmBuyRequest(BaseModel):
    tx_hash: str
    num_spins: int = Field(1, description="Solo 1 o 3 tiri extra", gt=0)

# ------------------------------------------------
# SETUP FASTAPI
# ------------------------------------------------
app = FastAPI(title="Gianky Coin Web App API")
app.mount("/static", StaticFiles(directory="static"), name="static")

IMAGE_PATH = "ruota.png"
if not os.path.exists(IMAGE_PATH):
    logging.error("File statico ruota.png non trovato!")

@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html>
      <head>
        <meta http-equiv="refresh" content="0; url=/static/index.html" />
      </head>
      <body>
      </body>
    </html>
    """

# Inizializza DB all'avvio
@app.on_event("startup")
def on_startup():
    init_db()

# ------------------------------------------------
# ENDPOINT PER FIRMA WALLET (Reown)
# ------------------------------------------------
@app.post("/api/auth/request_nonce")
async def request_nonce_api(req: AuthRequest):
    """Richiede un nonce da firmare."""
    nonce = str(random.randint(100000, 999999))
    session = Session()
    try:
        user = session.query(User).filter_by(wallet_address=req.wallet_address).first()
        if not user:
            user = User(wallet_address=req.wallet_address, telegram_id=req.telegram_id, extra_spins=0)
            session.add(user)
        user.nonce = nonce
        session.commit()
    except Exception as e:
        session.rollback()
        logging.error(f"Errore in request_nonce: {e}")
        raise HTTPException(status_code=500, detail="Errore durante la richiesta del nonce.")
    finally:
        session.close()
    return {"nonce": nonce}

@app.post("/api/auth/verify")
async def auth_verify_api(req: AuthVerifyRequest):
    """Verifica la firma del wallet."""
    session = Session()
    try:
        user = session.query(User).filter_by(wallet_address=req.wallet_address).first()
        if not user or not user.nonce:
            raise HTTPException(status_code=400, detail="Nonce non trovato o wallet inesistente.")
        message = f"GiankyStop: {user.nonce}"
        message_defunct = encode_defunct(text=message)

        recovered_address = w3.eth.account.recover_message(message_defunct, signature=req.signature)
        if recovered_address.lower() != req.wallet_address.lower():
            raise HTTPException(status_code=400, detail="Firma non valida o non combacia.")

        token = create_access_token({"wallet_address": req.wallet_address})
        user.nonce = None
        session.commit()
        return {"access_token": token, "token_type": "bearer"}

    except Exception as e:
        session.rollback()
        logging.error(f"Errore verify: {e}")
        raise HTTPException(status_code=500, detail="Errore nella verifica della firma.")
    finally:
        session.close()

# ------------------------------------------------
# ENDPOINT DI GIOCO, RUOTA, ECC.
# ------------------------------------------------
# Esempio se li avevi:
# @app.get('/api/ruota')...
# @app.post('/api/spin')...
# @app.post('/api/buyspins')...
# @app.post('/api/confirmbuy')...
# ecc.

# Avvio server
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
