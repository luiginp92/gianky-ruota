#!/usr/bin/env python3
"""
GiankyCoin Web App – main.py
-----------------------------
Mantiene il codice originale (logica di gioco, DB, ecc.) e aggiunge
il supporto a Reown AppKit per connettere e autenticare il wallet.
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
from eth_account.messages import encode_defunct

# Per JWT
from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer

# Importa modulo del database
from database import Session, User, PremioVinto, GlobalCounter, init_db

logging.basicConfig(level=logging.INFO)

# ---- Blockchain e Config ----
POLYGON_RPC = "https://polygon-rpc.com"
WALLET_DISTRIBUZIONE = "0xBc0c054066966a7A6C875981a18376e2296e5815"
CONTRATTO_GKY = "0x370806781689E670f85311700445449aC7C3Ff7a"
PRIVATE_KEY = os.getenv("PRIVATE_KEY_GKY")
if not PRIVATE_KEY:
    raise ValueError("❌ Errore: la chiave privata non è impostata.")

w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
w3.middleware_onion.inject(Web3.middleware.geth_poa_middleware, layer=0)

# ---- JWT e Sicurezza ----
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

# ---- FastAPI Config ----
app = FastAPI(title="GiankyCoin Web App API")

# Monta cartella static
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def home():
    # Reindirizza alla pagina index.html
    return """
    <html>
      <head>
        <meta http-equiv="refresh" content="0; url=/static/index.html" />
      </head>
      <body></body>
    </html>
    """

# Inizializza DB all'avvio
@app.on_event("startup")
def on_startup():
    init_db()

# ---- API per wallet connect con Reown ----
@app.post("/api/auth/request_nonce")
async def request_nonce(wallet_address: str):
    """
    Riceve un indirizzo wallet e genera un nonce da firmare.
    """
    nonce = str(random.randint(100000, 999999))
    session = Session()
    try:
        user = session.query(User).filter_by(wallet_address=wallet_address).first()
        if not user:
            user = User(wallet_address=wallet_address, extra_spins=0)
            session.add(user)
        user.nonce = nonce
        session.commit()
    except Exception as e:
        session.rollback()
        logging.error(f"Errore in request_nonce: {e}")
        raise HTTPException(status_code=500, detail="Errore durante la generazione del nonce.")
    finally:
        session.close()
    return {"nonce": nonce}

@app.post("/api/auth/verify")
async def auth_verify(wallet_address: str, signature: str):
    """
    Verifica la firma per autenticare il wallet.
    """
    session = Session()
    try:
        user = session.query(User).filter_by(wallet_address=wallet_address).first()
        if not user or not user.nonce:
            raise HTTPException(status_code=400, detail="Nonce non presente. Richiedi prima /api/auth/request_nonce")
        message = encode_defunct(text=user.nonce)

        recovered_address = w3.eth.account.recover_message(message, signature=signature)
        if recovered_address.lower() != wallet_address.lower():
            raise HTTPException(status_code=400, detail="Firma non valida")

        # Genera il token JWT
        access_token = create_access_token({"wallet_address": wallet_address})
        user.nonce = None
        session.commit()
        return {"access_token": access_token, "token_type": "bearer"}
    except Exception as e:
        session.rollback()
        logging.error(f"Errore in verify: {e}")
        raise HTTPException(status_code=500, detail="Errore durante la verifica firma")
    finally:
        session.close()

# ---- QUI Mettiamo TUTTA la logica di Gioco, Ruota, Acquisti, etc. ----
# (Mantieni i tuoi endpoint originali)
# Esempio:
"""
@app.get('/api/ruota')
def api_ruota(...):
    ...
"""

# Avvio server
if __name__ == '__main__':
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
