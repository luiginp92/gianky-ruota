#!/usr/bin/env python3
"""
Gianky Coin Mini App - main.py
--------------------------------
Questa mini app permette di:
  - Collegare il wallet
  - Visualizzare il saldo dei token Gianky Coin (e POL, se implementato) su rete Polygon
  - Acquistare giri extra
"""

import os
import logging
import datetime
import pytz
from flask import Flask, render_template, request, redirect, url_for, flash
from web3 import Web3

from database import Session, User, GlobalCounter  # Assicurati che le tue classi esistano in database.py

# Inizializza l'app Flask
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "s3cr3t!")  # Sostituisci con una chiave sicura

# Configurazione logging
logging.basicConfig(level=logging.INFO)

# Configurazione Blockchain
POLYGON_RPC = "https://polygon-rpc.com"
w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
if not w3.isConnected():
    logging.error("❌ Errore: Blockchain non connessa!")

# Parametri del contratto Gianky Coin
CONTRATTO_GKY = "0x370806781689E670f85311700445449aC7C3Ff7a"
WALLET_DISTRIBUZIONE = "0xBc0c054066966a7A6C875981a18376e2296e5815"
PRIVATE_KEY = os.getenv("PRIVATE_KEY_GKY")
if not PRIVATE_KEY:
    raise ValueError("❌ Errore: la chiave privata non è impostata.")

# ABI per il contratto ERC20 (con funzioni transfer e balanceOf)
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

# ROUTES DELLA MINI APP

@app.route("/")
def index():
    return render_template("index.html")  # Crea un semplice index.html in /templates

@app.route("/connect", methods=["GET", "POST"])
def connect():
    if request.method == "POST":
        wallet_address = request.form.get("wallet_address")
        # Per semplicità, chiediamo anche un "user_id" (che può essere il telegram_id)
        user_id = request.form.get("user_id")
        if not wallet_address or not Web3.isAddress(wallet_address):
            flash("Indirizzo wallet non valido.", "danger")
            return redirect(url_for("connect"))
        session = Session()
        try:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if not user:
                user = User(telegram_id=user_id, wallet_address=wallet_address, extra_spins=0)
                session.add(user)
            else:
                user.wallet_address = wallet_address
            session.commit()
            flash("Wallet collegato con successo!", "success")
            return redirect(url_for("balance", user_id=user_id))
        except Exception as e:
            logging.error(f"Errore connessione wallet: {e}")
            session.rollback()
            flash("Errore durante la connessione del wallet.", "danger")
        finally:
            session.close()
    return render_template("connect.html")

@app.route("/balance")
def balance():
    user_id = request.args.get("user_id")
    if not user_id:
        flash("ID utente mancante.", "danger")
        return redirect(url_for("index"))
    session = Session()
    try:
        user = session.query(User).filter_by(telegram_id=user_id).first()
        if not user or not user.wallet_address:
            flash("Wallet non collegato. Collegalo prima.", "warning")
            return redirect(url_for("connect"))
        gky_balance = get_token_balance(user.wallet_address)
        # Se hai un token POL, qui potresti chiamare una funzione simile per recuperarne il saldo
        pol_balance = 0  # Placeholder
        return render_template("balance.html", wallet=user.wallet_address,
                               gky_balance=gky_balance, pol_balance=pol_balance,
                               user_id=user_id)
    finally:
        session.close()

@app.route("/buyspins", methods=["GET", "POST"])
def buyspins():
    if request.method == "POST":
        user_id = request.form.get("user_id")
        try:
            num_spins = int(request.form.get("num_spins", 1))
        except ValueError:
            flash("Numero di tiri non valido.", "danger")
            return redirect(url_for("buyspins"))
        if num_spins not in [1, 3]:
            flash("Puoi acquistare solo 1 o 3 tiri extra.", "danger")
            return redirect(url_for("buyspins"))
        cost = 50 if num_spins == 1 else 125
        flash(f"Per acquistare {num_spins} tiri extra, trasferisci {cost} GKY al portafoglio: {WALLET_DISTRIBUZIONE}. "
              "Dopo la transazione, conferma inserendo il TX hash.", "info")
        return redirect(url_for("confirmbuy", user_id=user_id, cost=cost, num_spins=num_spins))
    return render_template("buyspins.html")

@app.route("/confirmbuy", methods=["GET", "POST"])
def confirmbuy():
    user_id = request.args.get("user_id")
    cost = request.args.get("cost")
    num_spins = request.args.get("num_spins")
    if request.method == "POST":
        tx_hash = request.form.get("tx_hash")
        session = Session()
        try:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if not user or not user.wallet_address:
                flash("Wallet non collegato.", "warning")
                return redirect(url_for("connect"))
            # QUI: Implementa la verifica della transazione (simile alla funzione verifica_transazione_gky del bot)
            # Per semplicità, assumiamo la transazione valida
            user.extra_spins = (user.extra_spins or 0) + int(num_spins)
            session.commit()
            # Aggiorna il contatore globale
            counter = session.query(GlobalCounter).first()
            if counter:
                counter.total_in += float(cost)
            else:
                counter = GlobalCounter(total_in=float(cost), total_out=0.0)
                session.add(counter)
            session.commit()
            flash("Acquisto confermato! Extra tiri aggiornati.", "success")
            return redirect(url_for("balance", user_id=user_id))
        except Exception as e:
            logging.error(f"Errore in confirmbuy: {e}")
            session.rollback()
            flash("Errore durante la conferma degli extra tiri.", "danger")
        finally:
            session.close()
    return render_template("confirmbuy.html", user_id=user_id, cost=cost, num_spins=num_spins)

if __name__ == "__main__":
    app.run(debug=True)
