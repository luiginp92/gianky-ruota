#!/usr/bin/env python3
"""
Gianky Coin Mini App - main.py
--------------------------------
Questa mini app (basata su FastAPI) permette di:
  - Collegare il wallet
  - Visualizzare il saldo dei token Gianky Coin (e POL, se implementato)
  - Acquistare giri extra
"""

import os
import logging
import pytz
from fastapi import FastAPI, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from web3 import Web3
from database import Session, User, GlobalCounter  # Assicurati che queste classi siano definite

app = FastAPI()
templates = Jinja2Templates(directory="templates")
logging.basicConfig(level=logging.INFO)

# Configurazione Blockchain
POLYGON_RPC = "https://polygon-rpc.com"
w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
if not w3.isConnected():
    logging.error("❌ Errore: Blockchain non connessa!")

# Parametri del contratto
CONTRATTO_GKY = "0x370806781689E670f85311700445449aC7C3Ff7a"
WALLET_DISTRIBUZIONE = "0xBc0c054066966a7A6C875981a18376e2296e5815"
PRIVATE_KEY = os.getenv("PRIVATE_KEY_GKY")
if not PRIVATE_KEY:
    raise ValueError("❌ Errore: la chiave privata non è impostata.")

# ABI per il contratto ERC20
ERC20_ABI = [
    {
        "constant": False,
        "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    }
]

contract = w3.eth.contract(address=CONTRATTO_GKY, abi=ERC20_ABI)

def get_token_balance(wallet_address):
    try:
        balance = contract.functions.balanceOf(wallet_address).call()
        return balance / 10**18
    except Exception as e:
        logging.error(f"Errore nel recupero del saldo: {e}")
        return None

def invia_token(destinatario, quantita):
    try:
        gas_price = w3.eth.gas_price
        tx = contract.functions.transfer(destinatario, int(quantita * 10**18)).buildTransaction({
            'from': WALLET_DISTRIBUZIONE,
            'nonce': w3.eth.get_transaction_count(WALLET_DISTRIBUZIONE),
            'gas': 100000,
            'gasPrice': gas_price,
        })
        signed = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
        logging.info(f"Token inviati: {quantita} GKY, TX: {tx_hash.hex()}")
        session = Session()
        try:
            counter = session.query(GlobalCounter).first()
            if counter:
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
    except Exception as e:
        logging.error(f"Errore invio token: {e}")
        return False

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/connect", response_class=HTMLResponse)
async def connect_get(request: Request):
    return templates.TemplateResponse("connect.html", {"request": request})

@app.post("/connect")
async def connect_post(request: Request, wallet_address: str = Form(...), user_id: str = Form(...)):
    if not wallet_address or not Web3.isAddress(wallet_address):
        # In assenza di un sistema di flash, reindirizza alla pagina connect
        return RedirectResponse(url="/connect", status_code=status.HTTP_302_FOUND)
    session = Session()
    try:
        user = session.query(User).filter_by(telegram_id=user_id).first()
        if not user:
            user = User(telegram_id=user_id, wallet_address=wallet_address, extra_spins=0)
            session.add(user)
        else:
            user.wallet_address = wallet_address
        session.commit()
    except Exception as e:
        logging.error(f"Errore connessione wallet: {e}")
        session.rollback()
    finally:
        session.close()
    return RedirectResponse(url=f"/balance?user_id={user_id}", status_code=status.HTTP_302_FOUND)

@app.get("/balance", response_class=HTMLResponse)
async def balance(request: Request, user_id: str):
    session = Session()
    try:
        user = session.query(User).filter_by(telegram_id=user_id).first()
        if not user or not user.wallet_address:
            return RedirectResponse(url="/connect", status_code=status.HTTP_302_FOUND)
        gky_balance = get_token_balance(user.wallet_address)
        # Per semplicità, pol_balance è impostato a 0
        return templates.TemplateResponse("balance.html", {
            "request": request,
            "wallet": user.wallet_address,
            "gky_balance": gky_balance,
            "pol_balance": 0,
            "user_id": user_id
        })
    finally:
        session.close()

# Aggiungi ulteriori endpoint per /buyspins e /confirmbuy se necessario...
