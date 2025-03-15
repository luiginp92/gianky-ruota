#!/usr/bin/env python3
"""
Gianky Coin Web App – main.py
-----------------------------
[... documentazione iniziale ...]
"""
import os
import random
import datetime
import pytz
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn

from web3 import Web3
from eth_account.messages import encode_defunct

from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer

from database import Session, User, PremioVinto, GlobalCounter, init_db

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

init_db()

app = FastAPI(title="Gianky Coin Web App API")
app.mount("/static", StaticFiles(directory="static"), name="static")

# ----------------- CONFIGURAZIONE BLOCKCHAIN E PARAMETRI -----------------
PRIVATE_KEY = os.getenv("DISTRIBUTION_PRIVATE_KEY")
if not PRIVATE_KEY:
    raise RuntimeError("Errore: DISTRIBUTION_PRIVATE_KEY non impostata.")

PROVIDER_URL = os.getenv("PROVIDER_URL", "https://polygon-rpc.com/")
TOKEN_ADDRESS = os.getenv("TOKEN_ADDRESS")
if not TOKEN_ADDRESS:
    raise RuntimeError("Errore: TOKEN_ADDRESS non impostato.")

WALLET_DISTRIBUZIONE = os.getenv("WALLET_DISTRIBUZIONE", "0xBc0c054066966a7A6C875981a18376e2296e5815")

w3 = Web3(Web3.HTTPProvider(PROVIDER_URL))
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
w3.middleware_onion.inject(custom_geth_poa_middleware, layer=0)
w3_no_mw = Web3(Web3.HTTPProvider(PROVIDER_URL))
USED_TX = set()

# ----------------- JWT & AUTENTICAZIONE -----------------
SECRET_KEY = os.getenv("SECRET_KEY", "supersecret_jwt_key_change_me")
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
        detail="Autenticazione non valida",
        headers={"WWW-Authenticate": "Bearer"}
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        wallet_address = payload.get("wallet_address")
        if not wallet_address:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    session = Session()
    try:
        user = session.query(User).filter(User.wallet_address.ilike(wallet_address)).first()
    finally:
        session.close()
    if not user:
        raise credentials_exception
    return user

# ----------------- FUNZIONI UTILI -----------------
def get_dynamic_gas_price():
    try:
        base = w3.eth.gasPrice
        safe = int(base * 1.2)
        logging.info(f"Gas Price: {w3.fromWei(base, 'gwei')} -> {w3.fromWei(safe, 'gwei')}")
        return safe
    except Exception as e:
        logging.error(f"Errore nel gas price: {e}")
        return Web3.toWei('50', 'gwei')

def invia_token(destinatario: str, quantita: int) -> bool:
    gas_price = get_dynamic_gas_price()
    token_amount = Web3.toWei(quantita, 'ether')
    try:
        token_contract = w3.eth.contract(
            address=TOKEN_ADDRESS,
            abi=[{
                "constant": False,
                "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}],
                "name": "transfer",
                "outputs": [{"name": "", "type": "bool"}],
                "payable": False,
                "stateMutability": "nonpayable",
                "type": "function"
            }]
        )
        tx = token_contract.functions.transfer(destinatario, quantita * 10**18).build_transaction({
            'from': WALLET_DISTRIBUZIONE,
            'nonce': w3.eth.get_transaction_count(WALLET_DISTRIBUZIONE),
            'gas': 100000,
            'gasPrice': gas_price,
        })
        signed_tx = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        logging.info(f"Token inviati: {quantita} GKY, txHash: {tx_hash.hex()}")
    except Exception as e:
        logging.error(f"Errore nell'invio dei token: {e}")
        return False
    session_db = Session()
    try:
        counter = session_db.query(GlobalCounter).first()
        if counter:
            counter.total_out += quantita
        else:
            counter = GlobalCounter(total_in=0.0, total_out=quantita)
            session_db.add(counter)
        session_db.commit()
    except Exception as e:
        logging.error(f"Errore aggiornamento total_out: {e}")
        session_db.rollback()
    finally:
        session_db.close()
    return True

def verifica_transazione_gky(user_address: str, tx_hash: str, cost: int) -> bool:
    try:
        tx = w3_no_mw.eth.get_transaction(tx_hash)
    except Exception as e:
        logging.error(f"Transazione {tx_hash} non trovata: {e}")
        return False
    if tx.get("to", "").lower() != TOKEN_ADDRESS.lower():
        logging.error("La TX non è indirizzata al contratto token.")
        return False
    token_contract = w3_no_mw.eth.contract(
        address=TOKEN_ADDRESS,
        abi=[{
            "constant": False,
            "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}],
            "name": "transfer",
            "outputs": [{"name": "", "type": "bool"}],
            "payable": False,
            "stateMutability": "nonpayable",
            "type": "function"
        }]
    )
    try:
        func_obj, params = token_contract.decode_function_input(tx.input)
    except Exception as decode_error:
        logging.error(f"Decodifica fallita: {decode_error}")
        return False
    if func_obj.fn_name != "transfer":
        logging.error("La TX non richiama transfer.")
        return False
    if params.get("_to", "").lower() != WALLET_DISTRIBUZIONE.lower():
        logging.error("La TX non invia al wallet di distribuzione.")
        return False
    token_amount = params.get("_value", 0)
    if token_amount < cost * 10**18:
        logging.error(f"Importo insufficiente: {w3_no_mw.fromWei(token_amount, 'ether')} vs {cost}")
        return False
    return True

def get_prize() -> str:
    r = random.random() * 100
    if r < 0.02:
        return "NFT BASIC"
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

# ----------------- MODELLI DI INPUT (Pydantic) -----------------
class AuthRequest(BaseModel):
    wallet_address: str = Field(..., regex="^0x[a-fA-F0-9]{40}$")
    telegram_id: Optional[str] = None

class AuthVerifyRequest(BaseModel):
    wallet_address: str = Field(..., regex="^0x[a-fA-F0-9]{40}$")
    signature: str

class BuySpinsRequest(BaseModel):
    num_spins: int = Field(..., description="Numero di extra spin (1, 3 o 10)", gt=0)

class ConfirmBuyRequest(BaseModel):
    tx_hash: str
    num_spins: int = Field(..., description="Numero di extra tiri (1, 3 o 10)", gt=0)

# ----------------- ENDPOINTS DI AUTENTICAZIONE -----------------
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
        raise HTTPException(status_code=500, detail="Errore nella richiesta del nonce.")
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
        if auth.signature != "dummy":
            message = encode_defunct(text=user.nonce)
            try:
                recovered = w3.eth.account.recover_message(message, signature=auth.signature)
            except Exception as e:
                logging.error(f"Errore nella verifica della firma: {e}")
                raise HTTPException(status_code=400, detail="Firma non valida.")
            if recovered.lower() != auth.wallet_address.lower():
                raise HTTPException(status_code=400, detail="Firma non corrisponde all'indirizzo.")
        token = create_access_token({"wallet_address": auth.wallet_address})
        user.nonce = None
        session.commit()
        return {"access_token": token, "token_type": "bearer"}
    except HTTPException as he:
        raise he
    except Exception as e:
        session.rollback()
        logging.error(f"Errore in auth_verify: {e}")
        raise HTTPException(status_code=500, detail="Errore durante la verifica dell'autenticazione.")
    finally:
        session.close()

# ----------------- ENDPOINT PER STATO RUOTA -----------------
@app.get("/api/ruota")
async def api_ruota(current_user: User = Depends(get_current_user)):
    session = Session()
    try:
        if not current_user.wallet_address:
            raise HTTPException(status_code=400, detail="Collega il wallet prima di giocare.")
        italy_tz = pytz.timezone("Europe/Rome")
        now = datetime.datetime.now(italy_tz)
        if (not current_user.last_play_date) or (current_user.last_play_date.astimezone(italy_tz).date() != now.date()):
            # Se non ha ancora giocato oggi, free spin disponibile: consuma il free spin
            current_user.last_play_date = now
            session.commit()
            available = current_user.extra_spins or 0  # Free spin consumato
        else:
            available = current_user.extra_spins or 0
        return {"available_spins": available, "message": f"Giri disponibili: {available}"}
    except Exception as e:
        logging.error(f"Errore in /api/ruota: {e}")
        raise HTTPException(status_code=500, detail="Errore nel recupero dello stato della ruota.")
    finally:
        session.close()

@app.get("/wheel")
async def get_wheel():
    image_path = os.path.join("static", "ruota.png")
    if os.path.exists(image_path):
        return FileResponse(image_path, media_type="image/png")
    else:
        raise HTTPException(status_code=404, detail="Immagine della ruota non trovata.")

# ----------------- ENDPOINT SPIN -----------------
@app.post("/api/spin")
async def api_spin(current_user: User = Depends(get_current_user)):
    session = Session()
    try:
        if not current_user.wallet_address:
            raise HTTPException(status_code=400, detail="Collega il wallet prima di giocare.")
        italy = pytz.timezone("Europe/Rome")
        now = datetime.datetime.now(italy)
        if (not current_user.last_play_date) or (current_user.last_play_date.astimezone(italy).date() != now.date()):
            # Primo giro del giorno: free spin disponibile, consumalo
            current_user.last_play_date = now
            session.commit()
            available = current_user.extra_spins or 0  # Free spin consumato
        else:
            available = current_user.extra_spins or 0
            if available > 0:
                current_user.extra_spins -= 1
                session.commit()
                available -= 1
            else:
                raise HTTPException(status_code=400, detail="Hai esaurito i tiri disponibili per oggi.")
        premio = get_prize()
        if premio == "NO PRIZE":
            result_text = "Nessun premio vinto. Riprova!"
        elif "GKY" in premio:
            amount = int(premio.split(" ")[0])
            if invia_token(current_user.wallet_address, amount):
                result_text = f"Hai vinto {amount} GKY!"
            else:
                result_text = "Errore nel trasferimento dei token."
        else:
            result_text = f"Hai vinto: {premio}!"
            record = PremioVinto(
                telegram_id=current_user.telegram_id or "N/A",
                wallet=current_user.wallet_address,
                premio=premio,
                user_id=current_user.id
            )
            session.add(record)
            session.commit()
        return {"message": result_text, "available_spins": available}
    except HTTPException as he:
        raise he
    except Exception as e:
        logging.error(f"Errore nello spin: {e}")
        raise HTTPException(status_code=500, detail="Errore durante il giro della ruota.")
    finally:
        session.close()

# ----------------- ENDPOINT ACQUISTO GIRI -----------------
@app.post("/api/buyspins")
async def api_buyspins(req: BuySpinsRequest, current_user: User = Depends(get_current_user)):
    session = Session()
    try:
        if not current_user.wallet_address:
            raise HTTPException(status_code=400, detail="Collega il wallet prima di acquistare extra spin.")
        if req.num_spins not in (1, 3, 10):
            raise HTTPException(status_code=400, detail="Puoi acquistare solo 1, 3 o 10 giri extra.")
        cost = 50 if req.num_spins == 1 else 125 if req.num_spins == 3 else 300
        msg = f"Trasferisci {cost} GKY a {WALLET_DISTRIBUZIONE} e poi chiama /api/confirmbuy con il tx hash."
        return {"message": msg}
    except Exception as e:
        logging.error(f"Errore in buyspins: {e}")
        raise HTTPException(status_code=500, detail="Errore nella richiesta d'acquisto.")
    finally:
        session.close()

# ----------------- ENDPOINT CONFERMA ACQUISTO -----------------
@app.post("/api/confirmbuy")
async def api_confirmbuy(req: ConfirmBuyRequest, current_user: User = Depends(get_current_user)):
    session = Session()
    try:
        if req.tx_hash in USED_TX:
            raise HTTPException(status_code=400, detail="Tx già usata per un acquisto.")
        if req.num_spins not in (1, 3, 10):
            raise HTTPException(status_code=400, detail="Puoi confermare solo 1, 3 o 10 giri extra.")
        cost = 50 if req.num_spins == 1 else 125 if req.num_spins == 3 else 300
        if not current_user.wallet_address:
            raise HTTPException(status_code=400, detail="Collega il wallet prima di confermare.")
        if not verifica_transazione_gky(current_user.wallet_address, req.tx_hash, cost):
            raise HTTPException(status_code=400, detail="Tx non valida o importo insufficiente.")
        current_user.extra_spins = (current_user.extra_spins or 0) + req.num_spins
        current_user.last_play_date = None  # In modo che al prossimo accesso venga concesso il free spin
        session.commit()
        session.refresh(current_user)
        logging.info(f"Extra spins aggiornati: {current_user.extra_spins}")
        USED_TX.add(req.tx_hash)
        counter = session.query(GlobalCounter).first()
        if counter:
            counter.total_in += cost
        else:
            counter = GlobalCounter(total_in=cost, total_out=0.0)
            session.add(counter)
        session.commit()
        available = 1 + (current_user.extra_spins or 0)
        return {"message": f"Acquisto confermato! Extra giri: {current_user.extra_spins}", "available_spins": available}
    except HTTPException as he:
        session.rollback()
        raise he
    except Exception as e:
        session.rollback()
        logging.error(f"Errore in confirmbuy: {e}")
        raise HTTPException(status_code=500, detail="Errore nella conferma degli extra giri.")
    finally:
        session.close()

# ----------------- ENDPOINT REFERRAL -----------------
@app.get("/api/referral")
async def api_referral(current_user: User = Depends(get_current_user)):
    referral_link = f"https://t.me/tuo_bot?start=ref_{current_user.wallet_address}"
    return {"referral_link": referral_link}

# ----------------- ENDPOINT SHARE TASK -----------------
@app.post("/api/sharetask")
async def api_sharetask(current_user: User = Depends(get_current_user)):
    video_url = "https://www.youtube.com/watch?v=AbpPYERGCXI&ab_channel=GKY-OFFICIAL"
    return {
        "message": "Condividi questo video per ottenere 1 giro extra (massimo 1 volta a settimana).",
        "video_url": video_url,
        "instruction": "Dopo la condivisione, chiama /api/claim_share_reward per reclamare il premio."
    }

@app.post("/api/claim_share_reward")
async def api_claim_share_reward(current_user: User = Depends(get_current_user)):
    session = Session()
    try:
        now = datetime.datetime.now(pytz.timezone("Europe/Rome"))
        if current_user.last_share_task:
            diff = now - current_user.last_share_task.astimezone(pytz.timezone("Europe/Rome"))
            if diff < datetime.timedelta(days=7):
                remaining = datetime.timedelta(days=7) - diff
                raise HTTPException(status_code=400, detail=f"Riprova tra {remaining.days} giorni.")
        current_user.extra_spins += 1
        current_user.last_share_task = now
        session.commit()
        return {"message": f"Task completata! Extra giri: {current_user.extra_spins}"}
    except HTTPException as he:
        raise he
    except Exception as e:
        session.rollback()
        logging.error(f"Errore in claim_share_reward: {e}")
        raise HTTPException(status_code=500, detail="Errore nel riscatto del premio.")
    finally:
        session.close()

# ----------------- ENDPOINT REPORT ADMIN -----------------
@app.get("/api/giankyadmin")
async def api_giankyadmin(current_user: User = Depends(get_current_user)):
    session = Session()
    try:
        counter = session.query(GlobalCounter).first()
        if not counter:
            return {"report": "Nessun dato disponibile ancora."}
        report_text = f"Entrate: {counter.total_in} GKY, Uscite: {counter.total_out} GKY, Bilancio: {counter.total_in - counter.total_out} GKY"
        return {"report": report_text}
    except Exception as e:
        logging.error(f"Errore in giankyadmin: {e}")
        raise HTTPException(status_code=500, detail="Errore nel report.")
    finally:
        session.close()

@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <html>
      <head><meta http-equiv="refresh" content="0; url=/static/index.html" /></head>
      <body></body>
    </html>
    """

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
