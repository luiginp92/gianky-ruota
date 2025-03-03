#!/usr/bin/env python3
"""
Gianky Coin Web App – main.py
-----------------------------
Questa applicazione espone tramite API REST la logica del gioco:
  • /api/spin: registra lo spin e determina il premio (senza trasferimento)
  • /api/distribute: trasferisce il premio dal wallet di distribuzione al wallet dell’utente (se premio contiene "GKY")
  • /api/buyspins e /api/confirmbuy: per l’acquisto di extra tiri
  • /api/referral: per ottenere il referral link
  • /wheel: restituisce l’immagine della ruota
  • "/" reindirizza all’index statico
"""

import logging
import random
import datetime
import os
import pytz

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
import uvicorn

from web3 import Web3
from eth_account.messages import encode_defunct

from database import Session, User, PremioVinto, GlobalCounter, init_db

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)

# CONFIGURAZIONI BLOCKCHAIN E COSTANTI
POLYGON_RPC = "https://polygon-rpc.com"
WALLET_DISTRIBUZIONE = "0xBc0c054066966a7A6C875981a18376e2296e5815"
CONTRATTO_GKY = "0x370806781689E670f85311700445449aC7C3Ff7a"
PRIVATE_KEY = os.getenv("PRIVATE_KEY_GKY")
if not PRIVATE_KEY:
    raise ValueError("❌ Errore: la chiave privata non è impostata.")

IMAGE_PATH = "ruota.png"
if os.path.exists(IMAGE_PATH):
    with open(IMAGE_PATH, "rb") as f:
        STATIC_IMAGE_BYTES = f.read()
else:
    STATIC_IMAGE_BYTES = None
    logging.error("File statico non trovato: ruota.png")

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

w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
w3.middleware_onion.inject(custom_geth_poa_middleware, layer=0)
w3_no_mw = Web3(Web3.HTTPProvider(POLYGON_RPC))

USED_TX = set()

app = FastAPI(title="Gianky Coin Web App API")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Gestore globale per errori di validazione
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logging.error(f"Validation error for {request.url}: {exc.errors()} - Body: {exc.body}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": exc.body},
    )

# MODELLI DI INPUT – wallet_address vincolato a 42 caratteri
class SpinRequest(BaseModel):
    wallet_address: str = Field(..., min_length=42, max_length=42)

class BuySpinsRequest(BaseModel):
    wallet_address: str = Field(..., min_length=42, max_length=42)
    num_spins: int = Field(..., description="Numero di extra spin (1, 3 o 10)", gt=0)

class ConfirmBuyRequest(BaseModel):
    wallet_address: str = Field(..., min_length=42, max_length=42)
    tx_hash: str
    num_spins: int = Field(..., description="Numero di tiri extra (1, 3 o 10)", gt=0)

class DistributePrizeRequest(BaseModel):
    wallet_address: str = Field(..., min_length=42, max_length=42)
    prize: str

def get_user(wallet_address: str):
    logging.info(f"Recupero utente per wallet: {wallet_address}")
    session = Session()
    try:
        user = session.query(User).filter(User.wallet_address.ilike(wallet_address)).first()
    except Exception as e:
        logging.error(f"Errore nella ricerca dell'utente: {e}")
        raise HTTPException(status_code=500, detail="Errore interno")
    finally:
        session.close()
    if user is None:
        logging.info("Utente non trovato, lo creo...")
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
        base = w3.eth.gas_price
        safe = int(base * 1.2)
        logging.info(f"Gas Price: {w3.from_wei(base, 'gwei')} -> {w3.from_wei(safe, 'gwei')}")
        return safe
    except Exception as e:
        logging.error(f"Errore nel gas price: {e}")
        return w3.to_wei('50', 'gwei')

def invia_token(destinatario, quantita):
    logging.info(f"Inizio trasferimento di {quantita} GKY a {destinatario}")
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
    logging.info(f"Transazione inviata, TX hash: {tx_hash.hex()}")
    
    session = Session()
    try:
        counter = session.query(GlobalCounter).first()
        if counter is not None:
            counter.total_out += quantita
        else:
            counter = GlobalCounter(total_in=0.0, total_out=quantita)
            session.add(counter)
        session.commit()
        logging.info("Contatore aggiornato correttamente.")
    except Exception as e:
        logging.error(f"Errore nell'aggiornamento del contatore: {e}")
        session.rollback()
    finally:
        session.close()
    return True

def verifica_transazione_gky(wallet_address, tx_hash, cost):
    logging.info(f"Inizio verifica TX per wallet {wallet_address} e costo {cost}")
    try:
        tx_hash = tx_hash.strip()
        if " " in tx_hash:
            parts = tx_hash.split()
            tx_hash = next((p for p in parts if p.startswith("0x")), tx_hash)
        if not tx_hash.startswith("0x"):
            logging.error("TX hash non valido: non inizia con '0x'")
            return False
        tx = w3_no_mw.eth.get_transaction(tx_hash)
        logging.info(f"TX recuperata, mittente: {tx['from']}")
        if tx["from"].lower() != wallet_address.lower():
            logging.error("TX non inviata dal wallet specificato.")
            return False
        if tx["to"].lower() != CONTRATTO_GKY.lower():
            logging.error("TX non destinata al contratto GKY.")
            return False
        contract = w3_no_mw.eth.contract(address=CONTRATTO_GKY, abi=[{
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
            logging.error(f"Importo insufficiente: {w3_no_mw.from_wei(token_amount, 'ether')} vs {cost}")
            return False
        logging.info("Verifica TX completata correttamente.")
        return True
    except Exception as e:
        logging.error(f"Errore nella verifica TX: {e}")
        return False

def get_prize():
    r = random.random() * 100
    logging.info(f"Random per premio: {r}")
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

@app.post("/api/spin")
async def api_spin(request: Request, spin_req: SpinRequest):
    raw_body = await request.body()
    logging.info(f"Raw request body in /api/spin: {raw_body}")
    logging.info(f"Ricevuta richiesta /api/spin con wallet_address: {spin_req.wallet_address}")
    user = get_user(spin_req.wallet_address)
    session = Session()
    try:
        italy_tz = pytz.timezone("Europe/Rome")
        now_italy = datetime.datetime.now(italy_tz)
        if (not user.last_play_date) or (user.last_play_date.astimezone(italy_tz).date() != now_italy.date()):
            available = 1 + (user.extra_spins or 0)
            user.last_play_date = now_italy
            session.commit()
            logging.info("Primo spin del giorno: impostati i giri disponibili.")
        else:
            available = user.extra_spins or 0
            if available > 0:
                user.extra_spins -= 1
                session.commit()
                available -= 1
                logging.info("Consumato un giro extra.")
            else:
                logging.error("Tiri esauriti per oggi.")
                raise HTTPException(status_code=400, detail="⚠️ Hai esaurito i tiri disponibili per oggi.")
        prize = get_prize()
        logging.info(f"Premio determinato: {prize}")
        if prize == "NO PRIZE":
            result_text = "😔 Nessun premio vinto. Riprova!"
        elif "GKY" in prize:
            result_text = f"🎉 Hai vinto {prize}!"
        else:
            result_text = f"🎉 Hai vinto: {prize}!"
            premio_record = PremioVinto(
                telegram_id=user.telegram_id or "N/A",
                wallet=user.wallet_address,
                premio=prize,
                user_id=user.id
            )
            session.add(premio_record)
            session.commit()
        logging.info(f"Spin completato per {user.wallet_address}. Giri residui: {available}")
        return {"message": result_text, "prize": prize, "available_spins": available}
    except HTTPException as he:
        logging.error(f"HTTPException in /api/spin: {he.detail}")
        raise he
    except Exception as e:
        logging.error(f"Errore in /api/spin: {e}")
        raise HTTPException(status_code=500, detail="Errore durante il giro della ruota.")
    finally:
        session.close()

@app.post("/api/distribute")
async def api_distribute(request: DistributePrizeRequest):
    logging.info(f"Ricevuta richiesta /api/distribute per wallet: {request.wallet_address} con premio: {request.prize}")
    user = get_user(request.wallet_address)
    if "GKY" in request.prize:
        try:
            amount = int(request.prize.split(" ")[0])
            logging.info(f"Importo da trasferire: {amount} GKY")
        except Exception:
            logging.error("Formato premio non valido in /api/distribute.")
            raise HTTPException(status_code=400, detail="Formato premio non valido.")
        if invia_token(user.wallet_address, amount):
            logging.info("Trasferimento completato con successo.")
            return {"message": f"Premio '{request.prize}' trasferito correttamente al wallet {user.wallet_address}."}
        else:
            logging.error("Errore nel trasferimento in /api/distribute.")
            raise HTTPException(status_code=500, detail="Errore nel trasferimento del premio.")
    else:
        logging.info("Premio non trasferibile, registrato in database.")
        return {"message": f"Premio '{request.prize}' registrato per il wallet {user.wallet_address}."}

@app.post("/api/buyspins")
async def api_buyspins(request: BuySpinsRequest):
    logging.info(f"Ricevuta richiesta /api/buyspins per wallet: {request.wallet_address} con num_spins: {request.num_spins}")
    user = get_user(request.wallet_address)
    session = Session()
    try:
        if request.num_spins not in [1, 3, 10]:
            raise HTTPException(status_code=400, detail="❌ Puoi acquistare solo 1, 3 o 10 tiri extra.")
        cost = 50 if request.num_spins == 1 else (125 if request.num_spins == 3 else 300)
        message = (f"✅ Per acquistare {request.num_spins} tiri extra, trasferisci {cost} GKY al portafoglio:\n"
                   f"{WALLET_DISTRIBUZIONE}")
        logging.info("Messaggio buyspins generato correttamente.")
        return {"message": message}
    except Exception as e:
        logging.error(f"Errore in /api/buyspins: {e}")
        raise HTTPException(status_code=500, detail="Errore durante la richiesta di acquisto degli extra spin.")
    finally:
        session.close()

@app.post("/api/confirmbuy")
async def api_confirmbuy(request: ConfirmBuyRequest):
    logging.info(f"Ricevuta richiesta /api/confirmbuy per wallet: {request.wallet_address} con tx_hash: {request.tx_hash}")
    user = get_user(request.wallet_address)
    session = Session()
    try:
        if request.tx_hash in USED_TX:
            raise HTTPException(status_code=400, detail="❌ Questa transazione è già stata usata per l'acquisto di extra tiri.")
        if request.num_spins not in [1, 3, 10]:
            raise HTTPException(status_code=400, detail="❌ Solo 1, 3 o 10 tiri extra sono ammessi.")
        cost = 50 if request.num_spins == 1 else (125 if request.num_spins == 3 else 300)
        logging.info(f"Verifica transazione per costo: {cost}")
        if verifica_transazione_gky(request.wallet_address, request.tx_hash, cost):
            user.extra_spins = (user.extra_spins or 0) + request.num_spins
            session.commit()
            USED_TX.add(request.tx_hash)
            counter = session.query(GlobalCounter).first()
            if counter is not None:
                counter.total_in += cost
            else:
                counter = GlobalCounter(total_in=cost, total_out=0.0)
                session.add(counter)
            session.commit()
            logging.info("Acquisto confermato correttamente.")
            return {"message": f"✅ Acquisto confermato! Extra tiri disponibili: {user.extra_spins}", "extra_spins": user.extra_spins}
        else:
            logging.error("Verifica transazione fallita in /api/confirmbuy.")
            raise HTTPException(status_code=400, detail="❌ Transazione non valida o importo insufficiente.")
    except HTTPException as he:
        logging.error(f"HTTPException in /api/confirmbuy: {he.detail}")
        raise he
    except Exception as e:
        logging.error(f"Errore in /api/confirmbuy: {e}")
        raise HTTPException(status_code=500, detail="Errore durante la conferma degli extra spin.")
    finally:
        session.close()

@app.get("/api/referral")
async def api_referral(wallet_address: str):
    referral_link = f"https://t.me/tuo_bot?start=ref_{wallet_address}"
    logging.info(f"Referral link generato per wallet: {wallet_address}")
    return {"referral_link": referral_link}

@app.get("/wheel")
async def get_wheel():
    if STATIC_IMAGE_BYTES:
        return FileResponse(IMAGE_PATH, media_type="image/png")
    else:
        raise HTTPException(status_code=404, detail="Immagine della ruota non trovata.")

@app.get("/", response_class=HTMLResponse)
async def home_redirect():
    return """
    <html>
      <head>
        <meta http-equiv="refresh" content="0; url=/static/index.html" />
      </head>
      <body></body>
    </html>
    """

@app.on_event("startup")
def on_startup_event():
    logging.info("Avvio applicazione e inizializzazione database...")
    init_db()
    logging.info("Database inizializzato.")

if __name__ == '__main__':
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
