#!/usr/bin/env python3
"""
Gianky Coin Mini App - main.py
--------------------------------
Questa mini app (basata su FastAPI) permette di:
  - Visualizzare la home servendo il file statico "index.html"
  - Gestire il collegamento del wallet tramite un form semplice
  - Visualizzare il saldo del wallet
"""

import os
import logging
import pytz
from fastapi import FastAPI, Request, Form, status
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from web3 import Web3
from database import Session, User, GlobalCounter  # Assicurati che queste classi siano definite

app = FastAPI()
logging.basicConfig(level=logging.INFO)

# Monta la cartella "static" per servire i file statici (incluso index.html)
app.mount("/static", StaticFiles(directory="static"), name="static")

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

@app.get("/", response_class=HTMLResponse)
async def index():
    # Serve il file "index.html" dalla cartella static
    return FileResponse("static/index.html")

# Endpoint per mostrare un semplice form di collegamento wallet
@app.get("/connect", response_class=HTMLResponse)
async def connect_get():
    html_content = """
    <html>
      <body>
        <h2>Collega il Wallet</h2>
        <form action="/connect" method="post">
          User ID: <input type="text" name="user_id" /><br/>
          Wallet Address: <input type="text" name="wallet_address" /><br/>
          <input type="submit" value="Invia" />
        </form>
      </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.post("/connect")
async def connect_post(user_id: str = Form(...), wallet_address: str = Form(...)):
    if not wallet_address or not Web3.isAddress(wallet_address):
        return HTMLResponse(content="<h3>Indirizzo wallet non valido</h3>", status_code=400)
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
        return HTMLResponse(content="<h3>Errore durante la connessione del wallet</h3>", status_code=500)
    finally:
        session.close()
    return RedirectResponse(url=f"/balance?user_id={user_id}", status_code=status.HTTP_302_FOUND)

# Endpoint per mostrare il saldo del wallet
@app.get("/balance", response_class=HTMLResponse)
async def balance(user_id: str):
    session = Session()
    try:
        user = session.query(User).filter_by(telegram_id=user_id).first()
        if not user or not user.wallet_address:
            return RedirectResponse(url="/connect", status_code=status.HTTP_302_FOUND)
        gky_balance = get_token_balance(user.wallet_address)
        html_content = f"""
        <html>
          <body>
            <h2>Saldo del Wallet</h2>
            <p>Wallet: {user.wallet_address}</p>
            <p>Saldo GKY: {gky_balance}</p>
            <p>Saldo POL: 0 (non implementato)</p>
          </body>
        </html>
        """
        return HTMLResponse(content=html_content)
    finally:
        session.close()

# Altri endpoint (ad es. per /buyspins, /confirmbuy) possono essere aggiunti in modo simile

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
