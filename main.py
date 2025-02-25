#!/usr/bin/env python3
"""
Gianky Coin Web App – main.py
-----------------------------
Questa applicazione espone tramite API REST la logica del gioco con:
 • Autenticazione basata sulla firma del wallet (JWT)
 • Validazioni robuste con Pydantic
 • Endpoints per gioco, acquisti, referral, ecc.
 • Un frontend minimale per interagire con il sistema
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

# ------------------------------------------------
# CONFIGURAZIONI DI BASE E LOGGING
# ------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# ------------------------------------------------
# CONFIGURAZIONI BLOCKCHAIN E COSTANTI
# ------------------------------------------------
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

# Middleware custom per POA (come nell'implementazione originale)
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

# Variabile globale per tx duplicate
USED_TX = set()

# ------------------------------------------------
# CONFIGURAZIONI JWT & AUTENTICAZIONE
# ------------------------------------------------
SECRET_KEY = "a_very_secret_key_change_me"  # In produzione usa una chiave sicura
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.datetime.utcnow() + expires_delta
    else:
        expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

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
        tx = w3_no_mw.eth.get_transaction(tx_hash)
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
        return True
    except Exception as e:
        logging.error(f"Errore verifica TX: {e}")
        return False

# ------------------------------------------------
# FUNZIONE get_prize() AGGIORNATA CON NUOVE % DEI PREMI
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
# CONFIGURAZIONE DI FASTAPI E MOUNT DEL FRONTEND STATICO
# ------------------------------------------------
app = FastAPI(title="Gianky Coin Web App API")
app.mount("/static", StaticFiles(directory="static"), name="static")

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

# ------------------------------------------------
# EVENTO DI STARTUP: INIZIALIZZAZIONE DEL DATABASE
# ------------------------------------------------
@app.on_event("startup")
def on_startup():
    init_db()

# ------------------------------------------------
# ENDPOINT DI AUTENTICAZIONE
# ------------------------------------------------
@app.post("/api/auth/request_nonce")
async def request_nonce(auth: AuthRequest):
    nonce = str(random.randint(100000, 999999))
    session = Session()
    try:
        user = session.query(User).filter_by(wallet_address=auth.wallet_address).first()
        if not user:
            user = User(wallet_address=auth.wallet_address, telegram_id=auth.telegram_id, extra_spins=0)
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
async def auth_verify(auth: AuthVerifyRequest):
    session = Session()
    try:
        user = session.query(User).filter_by(wallet_address=auth.wallet_address).first()
        if not user or not user.nonce:
            raise HTTPException(status_code=400, detail="Richiedi prima un nonce.")
        message = encode_defunct(text=user.nonce)
        try:
            recovered_address = w3.eth.account.recover_message(message, signature=auth.signature)
        except Exception as e:
            logging.error(f"Errore nella verifica della firma: {e}")
            raise HTTPException(status_code=400, detail="Firma non valida.")
        if recovered_address.lower() != auth.wallet_address.lower():
            raise HTTPException(status_code=400, detail="Firma non corrisponde all'indirizzo.")
        access_token = create_access_token(data={"wallet_address": auth.wallet_address})
        user.nonce = None
        session.commit()
        return {"access_token": access_token, "token_type": "bearer"}
    except HTTPException as he:
        raise he
    except Exception as e:
        session.rollback()
        logging.error(f"Errore in auth_verify: {e}")
        raise HTTPException(status_code=500, detail="Errore durante la verifica dell'autenticazione.")
    finally:
        session.close()

# ------------------------------------------------
# ENDPOINT DI GIOCO (protetti da token JWT)
# ------------------------------------------------
@app.get("/api/ruota")
async def api_ruota(current_user: User = Depends(get_current_user)):
    session = Session()
    try:
        if not current_user.wallet_address:
            raise HTTPException(status_code=400, detail="⚠️ Collega il wallet prima di giocare.")
        italy_tz = pytz.timezone("Europe/Rome")
        now_italy = datetime.datetime.now(italy_tz)
        if (not current_user.last_play_date) or (current_user.last_play_date.astimezone(italy_tz).date() != now_italy.date()):
            available = 1 + (current_user.extra_spins or 0)
        else:
            available = current_user.extra_spins or 0
        ruota_url = "/wheel" if STATIC_IMAGE_BYTES else None
        return {
            "message": f"🎰 Ruota pronta! Tiri disponibili: {available}",
            "available_spins": available,
            "ruota_image_url": ruota_url
        }
    except Exception as e:
        logging.error(f"Errore in ruota: {e}")
        raise HTTPException(status_code=500, detail="Errore durante il recupero dello stato della ruota.")
    finally:
        session.close()

@app.get("/wheel")
async def get_wheel():
    if STATIC_IMAGE_BYTES:
        return FileResponse(IMAGE_PATH, media_type="image/png")
    else:
        raise HTTPException(status_code=404, detail="Immagine della ruota non trovata.")

@app.post("/api/spin")
async def api_spin(current_user: User = Depends(get_current_user)):
    session = Session()
    try:
        if not current_user.wallet_address:
            raise HTTPException(status_code=400, detail="⚠️ Collega il wallet prima di giocare.")
        italy_tz = pytz.timezone("Europe/Rome")
        now_italy = datetime.datetime.now(italy_tz)
        if (not current_user.last_play_date) or (current_user.last_play_date.astimezone(italy_tz).date() != now_italy.date()):
            available = 1 + (current_user.extra_spins or 0)
            current_user.last_play_date = now_italy
            session.commit()
        else:
            available = current_user.extra_spins or 0
            if available > 0:
                current_user.extra_spins -= 1
                session.commit()
                available -= 1
            else:
                raise HTTPException(status_code=400, detail="⚠️ Hai esaurito i tiri disponibili per oggi.")
        prize = get_prize()
        if prize == "NO PRIZE":
            result_text = "😔 Nessun premio vinto. Riprova!"
        elif "GKY" in prize:
            amount = int(prize.split(" ")[0])
            if invia_token(current_user.wallet_address, amount):
                result_text = f"🎉 Hai vinto {amount} GKY!"
            else:
                result_text = "❌ Errore nell'invio dei token."
        else:
            result_text = f"🎉 Hai vinto: {prize}!"
            premio_record = PremioVinto(
                telegram_id=current_user.telegram_id or "N/A",
                wallet=current_user.wallet_address,
                premio=prize,
                user_id=current_user.id
            )
            session.add(premio_record)
            session.commit()
        return {
            "message": result_text,
            "available_spins": available
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        logging.error(f"Errore nello spin: {e}")
        raise HTTPException(status_code=500, detail="Errore durante il giro della ruota.")
    finally:
        session.close()

@app.post("/api/buyspins")
async def api_buyspins(request: BuySpinsRequest, current_user: User = Depends(get_current_user)):
    session = Session()
    try:
        if not current_user.wallet_address:
            raise HTTPException(status_code=400, detail="⚠️ Collega il wallet prima di acquistare extra spin.")
        if request.num_spins not in [1, 3]:
            raise HTTPException(status_code=400, detail="❌ Puoi acquistare solo 1 o 3 tiri extra.")
        cost = 50 if request.num_spins == 1 else 125
        message = (f"✅ Per acquistare {request.num_spins} tiri extra, trasferisci {cost} GKY al portafoglio:\n"
                   f"{WALLET_DISTRIBUZIONE}\n"
                   f"Quindi usa l'endpoint /api/confirmbuy con i dati della transazione.")
        return {"message": message}
    except Exception as e:
        logging.error(f"Errore in buyspins: {e}")
        raise HTTPException(status_code=500, detail="Errore durante la richiesta di acquisto degli extra spin.")
    finally:
        session.close()

@app.post("/api/confirmbuy")
async def api_confirmbuy(request: ConfirmBuyRequest, current_user: User = Depends(get_current_user)):
    session = Session()
    try:
        if request.tx_hash in USED_TX:
            raise HTTPException(status_code=400, detail="❌ Questa transazione è già stata usata per l'acquisto di extra tiri.")
        if request.num_spins not in [1, 3]:
            raise HTTPException(status_code=400, detail="❌ Solo 1 o 3 tiri extra sono ammessi.")
        cost = 50 if request.num_spins == 1 else 125
        if not current_user.wallet_address:
            raise HTTPException(status_code=400, detail="⚠️ Collega il wallet prima di confermare l'acquisto.")
        if verifica_transazione_gky(current_user.wallet_address, request.tx_hash, cost):
            current_user.extra_spins = (current_user.extra_spins or 0) + request.num_spins
            session.commit()
            USED_TX.add(request.tx_hash)
            counter = session.query(GlobalCounter).first()
            if counter is not None:
                counter.total_in += cost
            else:
                counter = GlobalCounter(total_in=cost, total_out=0.0)
                session.add(counter)
            session.commit()
            return {"message": f"✅ Acquisto confermato! Extra tiri disponibili: {current_user.extra_spins}"}
        else:
            raise HTTPException(status_code=400, detail="❌ Transazione non valida o importo insufficiente.")
    except HTTPException as he:
        raise he
    except Exception as e:
        logging.error(f"Errore in confirmbuy: {e}")
        raise HTTPException(status_code=500, detail="Errore durante la conferma degli extra spin.")
    finally:
        session.close()

@app.get("/api/referral")
async def api_referral(current_user: User = Depends(get_current_user)):
    referral_link = f"https://t.me/tuo_bot?start=ref_{current_user.wallet_address}"
    return {"referral_link": referral_link}

@app.post("/api/sharetask")
async def api_sharetask(current_user: User = Depends(get_current_user)):
    video_url = "https://www.youtube.com/watch?v=AbpPYERGCXI&ab_channel=GKY-OFFICIAL"
    return {
        "message": "📢 Condividi questo video per vincere 1 giro extra. (La task può essere completata 1 volta a settimana.)",
        "video_url": video_url,
        "instruction": "Dopo aver condiviso, usa l'endpoint /api/claim_share_reward."
    }

@app.post("/api/claim_share_reward")
async def api_claim_share_reward(current_user: User = Depends(get_current_user)):
    session = Session()
    try:
        now = datetime.datetime.now(pytz.timezone("Europe/Rome"))
        if current_user.last_share_task is not None:
            diff = now - current_user.last_share_task.astimezone(pytz.timezone("Europe/Rome"))
            if diff < datetime.timedelta(days=7):
                remaining = datetime.timedelta(days=7) - diff
                raise HTTPException(status_code=400, detail=f"⏳ Hai già completato la task. Riprova tra {remaining}.")
        current_user.extra_spins += 1
        current_user.last_share_task = now
        session.commit()
        return {"message": f"🎉 Task completata! Hai guadagnato 1 giro extra. Extra tiri disponibili: {current_user.extra_spins}"}
    except HTTPException as he:
        raise he
    except Exception as e:
        logging.error(f"Errore in claim_share_reward: {e}")
        raise HTTPException(status_code=500, detail="❌ Errore durante il riscatto del premio.")
    finally:
        session.close()

@app.get("/api/giankyadmin")
async def api_giankyadmin(current_user: User = Depends(get_current_user)):
    session = Session()
    try:
        counter = session.query(GlobalCounter).first()
        if counter is None:
            report_text = "Nessun dato disponibile ancora."
        else:
            total_in = counter.total_in
            total_out = counter.total_out
            report_text = (
                f"📊 Report Globali GKY:\n"
                f"Entrate totali: {total_in} GKY\n"
                f"Uscite totali: {total_out} GKY\n"
                f"Bilancio: {total_in - total_out} GKY"
            )
        return {"report": report_text}
    except Exception as e:
        logging.error(f"Errore nel report admin: {e}")
        raise HTTPException(status_code=500, detail="Errore durante la generazione del report.")
    finally:
        session.close()

# ------------------------------------------------
# Avvio dell'applicazione con uvicorn
# ------------------------------------------------
if __name__ == '__main__':
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
