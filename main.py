#!/usr/bin/env python3
"""
Gianky Coin Web App - main.py

Gestisce:
- L'avvio dell'app FastAPI
- La cartella /static con index.html e JS (incluso Reown)
- Endpoint per la firma del wallet (nonce + verify)
- Endpoint di esempio per la logica di gioco (spin)
"""

import os
import random
import datetime
import logging
import pytz
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn

# Librerie Web3 e firma
from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_account.messages import encode_defunct

# JWT e sicurezza
from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer

# Import DB e modelli
from database import Session, User, PremioVinto, GlobalCounter, init_db

logging.basicConfig(level=logging.INFO)

# --- Configurazioni Blockchain ---
POLYGON_RPC = "https://polygon-rpc.com"
WALLET_DISTRIBUZIONE = "0xBc0c054066966a7A6C875981a18376e2296e5815"
CONTRATTO_GKY = "0x370806781689E670f85311700445449aC7C3Ff7a"
PRIVATE_KEY = os.getenv("PRIVATE_KEY_GKY")

if not PRIVATE_KEY:
    raise ValueError("❌ Errore: la chiave privata non è impostata.")

# Inizializzazione Web3 con middleware POA (necessario per la rete Polygon)
w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
w3.middleware_onion.inject(geth_poa_middleware, layer=0)

# --- Configurazioni JWT ---
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

# --- Funzioni di utilità per la blockchain ---
def get_dynamic_gas_price():
    """Recupera un gas price basato su eth.gas_price, con un piccolo buffer."""
    try:
        base = w3.eth.gas_price
        safe = int(base * 1.2)
        logging.info(f"⛽ GasPrice base: {w3.from_wei(base, 'gwei')}, safe: {w3.from_wei(safe, 'gwei')}")
        return safe
    except Exception as e:
        logging.error(f"Errore nel gas price: {e}")
        return w3.to_wei('50', 'gwei')

def invia_token(destinatario: str, quantita: float):
    """Invia 'quantita' GKY (decimali=18) a 'destinatario'."""
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
    tx = contratto.functions.transfer(destinatario, int(quantita * 10**18)).build_transaction({
        'from': WALLET_DISTRIBUZIONE,
        'nonce': w3.eth.get_transaction_count(WALLET_DISTRIBUZIONE),
        'gas': 100000,
        'gasPrice': gas_price,
    })
    signed = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    logging.info(f"Token inviati: {quantita} GKY -> {destinatario}, TX: {tx_hash.hex()}")

    # Aggiorna contatore globale
    session = Session()
    try:
        counter = session.query(GlobalCounter).first()
        if not counter:
            counter = GlobalCounter(total_in=0.0, total_out=0.0)
            session.add(counter)
        counter.total_out += quantita
        session.commit()
    except Exception as e:
        logging.error(f"Errore aggiornamento total_out: {e}")
        session.rollback()
    finally:
        session.close()

    return True

def verifica_transazione_gky(user_address: str, tx_hash: str, cost: float):
    """Verifica che la transazione tx_hash abbia inviato almeno 'cost' GKY verso WALLET_DISTRIBUZIONE."""
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
            logging.error(f"Importo insufficiente {w3.from_wei(token_amount, 'ether')} vs {cost}")
            return False

        return True
    except Exception as e:
        logging.error(f"Errore verifica TX GKY: {e}")
        return False


# --- Funzione get_prize di esempio ---
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

# --- Modelli Pydantic per endpoints ---
class AuthRequest(BaseModel):
    wallet_address: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")
    telegram_id: Optional[str] = None

class AuthVerifyRequest(BaseModel):
    wallet_address: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")
    signature: str

# Se hai altri model per buyspins, confirmbuy, ecc.

# --- Inizializzazione FastAPI ---
app = FastAPI(title="Gianky Coin Web App API")

# Monta la cartella static (se index.html sta in /static)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Se vuoi servire un eventuale ruota.png
IMAGE_PATH = "ruota.png"
if not os.path.exists(IMAGE_PATH):
    logging.warning("Attenzione: ruota.png non trovato nella root del progetto.")

@app.get("/", response_class=HTMLResponse)
def home():
    # Reindirizza a /static/index.html (oppure potresti aprire un file in locale)
    return """
    <html>
      <head>
        <meta http-equiv="refresh" content="0; url=/static/index.html" />
      </head>
      <body>
      </body>
    </html>
    """

@app.on_event("startup")
def on_startup():
    logging.info("Avvio e inizializzazione DB...")
    init_db()


# --- Endpoints per firma wallet (nonce e verify) ---
@app.post("/api/auth/request_nonce")
def request_nonce_api(req: AuthRequest):
    nonce = str(random.randint(100000, 999999))
    session = Session()
    try:
        user = session.query(User).filter_by(wallet_address=req.wallet_address).first()
        if not user:
            user = User(wallet_address=req.wallet_address, telegram_id=req.telegram_id, extra_spins=0)
            session.add(user)
        user.nonce = nonce
        session.commit()
        return {"nonce": nonce}
    except Exception as e:
        session.rollback()
        logging.error(f"Errore in request_nonce: {e}")
        raise HTTPException(status_code=500, detail="Errore durante la richiesta del nonce.")
    finally:
        session.close()

@app.post("/api/auth/verify")
def auth_verify_api(req: AuthVerifyRequest):
    session = Session()
    try:
        user = session.query(User).filter_by(wallet_address=req.wallet_address).first()
        if not user or not user.nonce:
            raise HTTPException(status_code=400, detail="Nonce non trovato o wallet inesistente.")

        message = f"GiankyStop: {user.nonce}"
        msg_defunct = encode_defunct(text=message)
        recovered_address = w3.eth.account.recover_message(msg_defunct, signature=req.signature)

        if recovered_address.lower() != req.wallet_address.lower():
            raise HTTPException(status_code=400, detail="Firma non valida o non combacia.")

        # Genera token
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


# --- Endpoint di esempio "spin" per la ruota ---
@app.post("/api/spin")
def spin_api(current_user: User = Depends(get_current_user)):
    session = Session()
    try:
        # Esempio di check daily spin
        italy_tz = pytz.timezone("Europe/Rome")
        now_italy = datetime.datetime.now(italy_tz)

        if not current_user.last_play_date or current_user.last_play_date.astimezone(italy_tz).date() != now_italy.date():
            # Primo spin giornaliero gratuito
            available = 1 + (current_user.extra_spins or 0)
            current_user.last_play_date = now_italy
            session.commit()
        else:
            # Usa extra spins
            available = current_user.extra_spins or 0

        if available <= 0:
            raise HTTPException(status_code=400, detail="Nessun tiro disponibile.")

        if current_user.last_play_date and current_user.last_play_date.astimezone(italy_tz).date() == now_italy.date():
            # Sottrai 1 spin dal contatore extra (se >0)
            current_user.extra_spins = available - 1
            session.commit()

        # Calcola premio
        prize = get_prize()
        msg = ""
        if prize == "NO PRIZE":
            msg = "Nessun premio vinto!"
        elif "GKY" in prize:
            # Esempio "10 GKY"
            amount = int(prize.split(" ")[0])
            success = invia_token(current_user.wallet_address, amount)
            if success:
                msg = f"Hai vinto {amount} GKY!"
            else:
                msg = "Errore invio token."
        else:
            # NFT o altro
            msg = f"Hai vinto: {prize}"
            p = PremioVinto(
                telegram_id=current_user.telegram_id or "",
                wallet=current_user.wallet_address,
                premio=prize,
                user_id=current_user.id
            )
            session.add(p)
            session.commit()

        # Calcoliamo quanti spin rimangono
        spins_left = current_user.extra_spins or 0

        return {"message": msg, "available_spins": spins_left}

    except HTTPException as he:
        raise he
    except Exception as e:
        logging.error(f"Errore spin: {e}")
        raise HTTPException(status_code=500, detail="Errore durante spin.")
    finally:
        session.close()


# --- Avvio dell'app ---
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
