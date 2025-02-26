#!/usr/bin/env python3
"""
Gianky Coin Web App – main.py
-----------------------------
Mantiene la logica originale e aggiunge supporto a Reown AppKit per il collegamento ai wallet.
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

# Importa il modulo del database
from database import Session, User, PremioVinto, GlobalCounter, init_db

# Configurazione FastAPI
app = FastAPI(title="Gianky Coin Web App API")

# Monta la cartella static
app.mount("/static", StaticFiles(directory="static"), name="static")

# **🔹 CONFIGURAZIONE REOWN APPKIT**
PROJECT_ID = "c17f0d55c1fb5debe77f860c40b7afdb"  # Il tuo Project ID

# Configurazione blockchain (Polygon)
POLYGON_RPC = "https://polygon-rpc.com"
w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))

# **🔹 ENDPOINT AUTENTICAZIONE WALLET CON REOWN APPKIT**
class NonceRequest(BaseModel):
    wallet_address: str

class VerifyRequest(BaseModel):
    wallet_address: str
    signature: str

@app.post("/api/auth/request_nonce")
async def request_nonce(request: NonceRequest):
    wallet = request.wallet_address
    if not Web3.is_address(wallet):
        raise HTTPException(status_code=400, detail="Indirizzo wallet non valido")

    nonce = os.urandom(16).hex()
    session = Session()
    try:
        user = session.query(User).filter_by(wallet_address=wallet).first()
        if not user:
            user = User(wallet_address=wallet, extra_spins=0)
            session.add(user)
        user.nonce = nonce
        session.commit()
    except Exception as e:
        session.rollback()
        logging.error(f"Errore richiesta nonce: {e}")
        raise HTTPException(status_code=500, detail="Errore richiesta nonce")
    finally:
        session.close()
    
    return {"nonce": nonce}

@app.post("/api/auth/verify")
async def verify_signature(request: VerifyRequest):
    wallet = request.wallet_address
    signature = request.signature

    session = Session()
    try:
        user = session.query(User).filter_by(wallet_address=wallet).first()
        if not user or not user.nonce:
            raise HTTPException(status_code=400, detail="Nonce non trovato")

        message = f"GiankyStop: {user.nonce}"
        recovered_address = w3.eth.account.recover_message(
            Web3.solidityKeccak(['string'], [message]), signature=signature
        )

        if recovered_address.lower() != wallet.lower():
            raise HTTPException(status_code=400, detail="Firma non valida")

        access_token = jwt.encode({"wallet_address": wallet}, "a_very_secret_key", algorithm="HS256")
        user.nonce = None
        session.commit()
        return {"access_token": access_token, "token_type": "bearer"}

    except Exception as e:
        logging.error(f"Errore verifica firma: {e}")
        raise HTTPException(status_code=500, detail="Errore verifica firma")
    finally:
        session.close()

# **🔹 API ESISTENTI (RUOTA, ACQUISTI, TOKEN, ETC.)**
# Manteniamo il tuo codice originale qui senza modifiche

@app.get("/", response_class=HTMLResponse)
async def home():
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

# **🔹 AVVIO SERVER**
if __name__ == '__main__':
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
