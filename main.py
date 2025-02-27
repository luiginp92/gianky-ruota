#!/usr/bin/env python3
"""
Gianky Coin Mini App - main.py
--------------------------------
Questa mini app (basata su FastAPI) permette di:
  - Collegare il wallet
  - Visualizzare il saldo dei token (GKY) del wallet collegato
  - Acquistare extra giri (spins) mediante conferma della transazione
  - Visualizzare un report globale (admin)
"""

import os
import logging
from fastapi import FastAPI, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from web3 import Web3
from database import Session, User, GlobalCounter  # Assicurati che queste classi siano definite

app = FastAPI()
logging.basicConfig(level=logging.INFO)

# Monta la cartella "static" (eventuale per file CSS/immagini, se necessario)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Configurazione della blockchain
POLYGON_RPC = "https://polygon-rpc.com"
w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
if not w3.is_connected():
    logging.error("❌ Errore: Blockchain non connessa!")

# Parametri del contratto e chiave privata (da impostare tramite variabili d'ambiente o hardcoded)
CONTRATTO_GKY = "0x370806781689E670f85311700445449aC7C3Ff7a"
WALLET_DISTRIBUZIONE = "0xBc0c054066966a7A6C875981a18376e2296e5815"
PRIVATE_KEY = os.getenv("PRIVATE_KEY_GKY")
if not PRIVATE_KEY:
    raise ValueError("❌ Errore: la chiave privata non è impostata.")

# ABI semplificato per un token ERC20 (funzioni transfer e balanceOf)
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
async def home():
    html = """
    <!DOCTYPE html>
    <html lang="it">
    <head>
      <meta charset="UTF-8">
      <title>Gianky Coin Mini App</title>
    </head>
    <body>
      <h1>Benvenuto in Gianky Coin Mini App</h1>
      <ul>
        <li><a href="/connect">Collega il tuo wallet</a></li>
        <li><a href="/balance?user_id=YOUR_USER_ID">Visualizza saldo (sostituisci YOUR_USER_ID)</a></li>
        <li><a href="/buyspins?user_id=YOUR_USER_ID">Acquista extra giri (sostituisci YOUR_USER_ID)</a></li>
        <li><a href="/giankyadmin">Report Globale (Admin)</a></li>
      </ul>
    </body>
    </html>
    """
    return HTMLResponse(content=html)

@app.get("/connect", response_class=HTMLResponse)
async def connect_get():
    html = """
    <!DOCTYPE html>
    <html lang="it">
    <head>
      <meta charset="UTF-8">
      <title>Collega il Wallet</title>
    </head>
    <body>
      <h2>Collega il tuo Wallet</h2>
      <form action="/connect" method="post">
        User ID: <input type="text" name="user_id" /><br/>
        Wallet Address: <input type="text" name="wallet_address" /><br/>
        <input type="submit" value="Collega" />
      </form>
      <p><a href="/">Torna alla Home</a></p>
    </body>
    </html>
    """
    return HTMLResponse(content=html)

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
        logging.error(f"Errore nella connessione del wallet: {e}")
        session.rollback()
        return HTMLResponse(content="<h3>Errore durante la connessione del wallet</h3>", status_code=500)
    finally:
        session.close()
    return RedirectResponse(url=f"/balance?user_id={user_id}", status_code=status.HTTP_302_FOUND)

@app.get("/balance", response_class=HTMLResponse)
async def balance(user_id: str):
    session = Session()
    try:
        user = session.query(User).filter_by(telegram_id=user_id).first()
        if not user or not user.wallet_address:
            return RedirectResponse(url="/connect", status_code=status.HTTP_302_FOUND)
        gky_balance = get_token_balance(user.wallet_address)
        html = f"""
        <!DOCTYPE html>
        <html lang="it">
        <head>
          <meta charset="UTF-8">
          <title>Saldo del Wallet</title>
        </head>
        <body>
          <h2>Saldo del Wallet</h2>
          <p>Wallet: {user.wallet_address}</p>
          <p>Saldo GKY: {gky_balance}</p>
          <p>Saldo POL: 0 (non implementato)</p>
          <p><a href="/">Torna alla Home</a></p>
        </body>
        </html>
        """
        return HTMLResponse(content=html)
    finally:
        session.close()

@app.get("/buyspins", response_class=HTMLResponse)
async def buyspins_get(user_id: str):
    html = f"""
    <!DOCTYPE html>
    <html lang="it">
    <head>
      <meta charset="UTF-8">
      <title>Acquista Extra Giri</title>
    </head>
    <body>
      <h2>Acquista Extra Giri</h2>
      <p>Per acquistare extra giri:</p>
      <p>Trasferisci 50 GKY per 1 giro oppure 125 GKY per 3 giri al seguente wallet:</p>
      <p><strong>{WALLET_DISTRIBUZIONE}</strong></p>
      <p>Dopo il trasferimento, inserisci il TX hash per confermare l'acquisto:</p>
      <form action="/confirmbuy" method="post">
        <input type="hidden" name="user_id" value="{user_id}" />
        TX Hash: <input type="text" name="tx_hash" /><br/>
        Numero di giri (1 o 3): <input type="text" name="num_spins" /><br/>
        <input type="submit" value="Conferma Acquisto" />
      </form>
      <p><a href="/">Torna alla Home</a></p>
    </body>
    </html>
    """
    return HTMLResponse(content=html)

def verifica_transazione_gky(user_address, tx_hash, cost):
    try:
        tx = w3.eth.get_transaction(tx_hash)
        if tx["to"].lower() != CONTRATTO_GKY.lower():
            logging.error("TX non destinata al contratto GKY.")
            return False
        # Per semplicità, decodifichiamo l'input della funzione transfer
        contract_instance = w3.eth.contract(address=CONTRATTO_GKY, abi=[{
            "constant": False,
            "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}],
            "name": "transfer",
            "outputs": [{"name": "", "type": "bool"}],
            "payable": False,
            "stateMutability": "nonpayable",
            "type": "function",
        }])
        try:
            func_obj, params = contract_instance.decode_function_input(tx.input)
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
            logging.error(f"Importo insufficiente: {w3.fromWei(token_amount, 'ether')} vs {cost}")
            return False
        return True
    except Exception as e:
        logging.error(f"Errore verifica TX: {e}")
        return False

@app.post("/confirmbuy", response_class=HTMLResponse)
async def confirmbuy(user_id: str = Form(...), tx_hash: str = Form(...), num_spins: int = Form(...)):
    cost = 50 if num_spins == 1 else 125
    session = Session()
    try:
        user = session.query(User).filter_by(telegram_id=user_id).first()
        if not user or not user.wallet_address:
            return HTMLResponse(content="<h3>Wallet non collegato. Collega il wallet prima.</h3>")
        if verifica_transazione_gky(user.wallet_address, tx_hash, cost):
            user.extra_spins = (user.extra_spins or 0) + num_spins
            session.commit()
            counter = session.query(GlobalCounter).first()
            if counter:
                counter.total_in += cost
            else:
                counter = GlobalCounter(total_in=cost, total_out=0)
                session.add(counter)
            session.commit()
            return HTMLResponse(content=f"<h3>Acquisto confermato! Extra giri disponibili: {user.extra_spins}</h3><p><a href='/balance?user_id={user_id}'>Visualizza saldo</a></p>")
        else:
            return HTMLResponse(content="<h3>Transazione non valida o importo insufficiente.</h3>")
    except Exception as e:
        logging.error(f"Errore in confirmbuy: {e}")
        session.rollback()
        return HTMLResponse(content="<h3>Errore durante la conferma degli extra giri.</h3>", status_code=500)
    finally:
        session.close()

@app.get("/giankyadmin", response_class=HTMLResponse)
async def giankyadmin():
    session = Session()
    try:
        counter = session.query(GlobalCounter).first()
        if not counter:
            report = "Nessun dato disponibile ancora."
        else:
            total_in = counter.total_in
            total_out = counter.total_out
            report = f"Entrate totali: {total_in} GKY<br>Uscite totali: {total_out} GKY<br>Bilancio: {total_in - total_out} GKY"
        html = f"""
        <!DOCTYPE html>
        <html lang="it">
        <head>
          <meta charset="UTF-8">
          <title>Report Globale</title>
        </head>
        <body>
          <h2>Report Globale Gianky Coin</h2>
          <p>{report}</p>
          <p><a href="/">Torna alla Home</a></p>
        </body>
        </html>
        """
        return HTMLResponse(content=html)
    finally:
        session.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
