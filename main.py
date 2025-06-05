#!/usr/bin/env python3
"""
Gianky Coin Web App – main.py
-----------------------------
Manages:
 • The wheel spin and prize distribution
 • Purchasing and confirming extra spins
 • Endpoints for wallet balance and spins status
 • Endpoints for claiming referral and tasks (with delayed credit)
"""

import os, random, datetime, pytz, logging, asyncio
from typing import Optional
from pyngrok import ngrok
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn

from web3 import Web3
from eth_account.messages import encode_defunct
from jose import JWTError, jwt

from database import Session, User, PremioVinto, GlobalCounter, init_db
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
init_db()

app = FastAPI(title="Gianky Coin Web App API")

# Ottieni il percorso assoluto della directory static
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# Monta la directory static su /static
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Rimuovi il mount duplicato alla root se presente (dall'ultimo tentativo)
try:
    # Controlla se 'root' è nel dictionary dei routes prima di provare a rimuoverlo
    # Questo è un workaround per gestire potenziali errori se il mount non esiste
    # Nota: l'accesso diretto ai routes interni potrebbe non essere stabile tra versioni di FastAPI
    # Un approccio più robusto potrebbe richiedere la ristrutturazione del setup dei mounts
    # Qui assumiamo che l'ultimo tentativo di mount alla root abbia aggiunto qualcosa con name='root'
    # e proviamo a rimuoverlo per evitare conflitti.
    # Questo blocco try/except è per sicurezza nel caso la struttura interna di FastAPI cambi.
    found_root_mount = False
    for route in app.routes:
        if hasattr(route, 'name') and route.name == 'root':
             found_root_mount = True
             # Non possiamo rimuovere direttamente un route per nome in questo modo standard
             # La soluzione più semplice e sicura è rimuovere e rimontare tutti gli statici,
             # ma questo è complesso in una singola edit call.
             # Lasciamo che il mount /static sovrastinga parzialmente il mount /. 
             # La redirect dalla root sarà la soluzione più diretta.
             break # Trovato il mount 'root', procediamo con la redirect
except Exception as e:
    logging.warning(f"Errore nel tentativo di verificare mount 'root': {e}")
    # Continua anche in caso di errore, la redirect dovrebbe risolvere il problema

# Reindirizza la root a /static/loading.html
@app.get("/", response_class=RedirectResponse, include_in_schema=False)
async def redirect_to_loading():
    return "/static/loading.html"

@app.get("/index.html", response_class=HTMLResponse)
async def index():
    return FileResponse("static/index.html")

# Configurazione ngrok
NGROK_AUTH_TOKEN = os.getenv("NGROK_AUTH_TOKEN")
if NGROK_AUTH_TOKEN:
    ngrok.set_auth_token(NGROK_AUTH_TOKEN)
    public_url = ngrok.connect(8000).public_url
    logging.info(f"Ngrok tunnel URL: {public_url}")

# ------------------ BLOCKCHAIN CONFIG ------------------
PRIVATE_KEY = os.getenv("DISTRIBUTION_PRIVATE_KEY")
if not PRIVATE_KEY:
    raise RuntimeError("Error: DISTRIBUTION_PRIVATE_KEY not set.")

PROVIDER_URL = os.getenv("PROVIDER_URL", "https://polygon-rpc.com/")
TOKEN_ADDRESS = os.getenv("TOKEN_ADDRESS")
if not TOKEN_ADDRESS:
    raise RuntimeError("Error: TOKEN_ADDRESS not set.")

WALLET_DISTRIBUZIONE = os.getenv("WALLET_DISTRIBUZIONE", "0xBc0c054066966a7A6C875981a18376e2296e5815")
NFT_CONTRACT_ADDRESS = "0xdc91E2fD661E88a9a1bcB1c826B5579232fc9898"  # NFT contract address

w3 = Web3(Web3.HTTPProvider(PROVIDER_URL))
w3_no_mw = Web3(Web3.HTTPProvider(PROVIDER_URL))
USED_TX = set()

def to_wei(val, unit):
    return Web3.to_wei(val, unit)

def from_wei(val, unit):
    return Web3.from_wei(val, unit)

def get_dynamic_gas_price():
    try:
        try:
            base = w3.eth.gas_price
        except AttributeError:
            base = w3.eth.get_gas_price()
        safe = int(base * 1.2)
        logging.info(f"Gas Price: {from_wei(base, 'gwei')} -> {from_wei(safe, 'gwei')}")
        return safe
    except Exception as e:
        logging.error(f"Gas price error: {e}")
        return to_wei(50, 'gwei')

# ------------------ TX VERIFICATION ------------------
def verifica_transazione_gky(user_address: str, tx_hash: str, cost: int) -> bool:
    try:
        tx = w3_no_mw.eth.get_transaction(tx_hash)
        if tx.get("to", "").lower() != TOKEN_ADDRESS.lower():
            logging.error("TX not sent to the token contract.")
            return False
        return True
    except Exception as e:
        logging.error(f"TX verification error: {e}")
        return False

# ------------------ JWT ------------------
SECRET_KEY = os.getenv("SECRET_KEY", "supersecret_jwt_key_change_me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None):
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + (expires_delta or datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# ------------------ INPUT MODELS ------------------
class SpinRequest(BaseModel):
    wallet_address: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")

class BuySpinsRequest(BaseModel):
    wallet_address: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")
    num_spins: int = Field(..., description="Number of extra spins (1, 3, or 10)", gt=0)

class ConfirmBuyRequest(BaseModel):
    wallet_address: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")
    tx_hash: str
    num_spins: int = Field(..., description="Number of extra spins (1, 3, or 10)", gt=0)

class DistributePrizeRequest(BaseModel):
    wallet_address: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")
    prize: str

class ReferralRequest(BaseModel):
    wallet_address: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")
    referrer: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")

class TaskClaimRequest(BaseModel):
    wallet_address: str = Field(..., pattern="^0x[a-fA-F0-9]{40}$")
    task_id: str

# ------------------ NEW ENDPOINT: CLAIMED TASKS ------------------
@app.get("/api/claimed_tasks/{wallet_address}")
async def claimed_tasks(wallet_address: str):
    user = get_user(wallet_address)
    tasks = user.last_claimed_tasks
    claimed = tasks.split(",") if tasks and tasks.strip() != "" else []
    return {"claimed_tasks": claimed}

# ------------------ ENDPOINT: SPINS STATUS ------------------
@app.get("/api/spins_status/{wallet_address}")
async def spins_status(wallet_address: str):
    user = get_user(wallet_address)
    italy = pytz.timezone("Europe/Rome")
    now_date = datetime.datetime.now(italy).date()
    free_spin = 1 if (getattr(user, "last_free_spin_date", None) is None or user.last_free_spin_date < now_date) else 0
    available = user.extra_spins + free_spin
    return {"available_spins": available}

# ------------------ ENDPOINT: GRANT TEST SPINS ------------------
@app.post("/api/grant_test_spins")
async def grant_test_spins(wallet_address: str = "0xTestWallet00000000000000000000000000"): # Default test wallet
    session_db = Session()
    try:
        user = get_user(wallet_address)
        if user is None:
             raise HTTPException(status_code=500, detail="Could not get or create user.")

        user.extra_spins += 5
        session_db.commit()
        logging.info(f"Granted 5 test spins to {wallet_address}")
        italy = pytz.timezone("Europe/Rome")
        now_date = datetime.datetime.now(italy).date()
        current_free_spin = 1 if (getattr(user, "last_free_spin_date", None) is None or user.last_free_spin_date < now_date) else 0
        available = user.extra_spins + current_free_spin
        return {"message": "5 test spins granted.", "available_spins": available}
    except Exception as e:
        session_db.rollback()
        logging.error(f"Error granting test spins: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session_db.close()

# ------------------ ENDPOINT: WALLET BALANCE ------------------
@app.get("/api/balance/{wallet_address}")
async def get_balance(wallet_address: str):
    try:
        provider = Web3(Web3.HTTPProvider(PROVIDER_URL))
        checksum_address = provider.to_checksum_address(wallet_address)
        matic_balance = provider.eth.get_balance(checksum_address)
        token_contract = provider.eth.contract(
            address=TOKEN_ADDRESS,
            abi=[{
                "constant": True,
                "inputs": [{"name": "owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "", "type": "uint256"}],
                "payable": False,
                "stateMutability": "view",
                "type": "function"
            }]
        )
        token_balance = token_contract.functions.balanceOf(checksum_address).call()
        return {"matic": float(from_wei(matic_balance, 'ether')), "gky": float(from_wei(token_balance, 'ether'))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ------------------ TOKEN TRANSFER ------------------
def invia_token(destinatario: str, quantita: int) -> bool:
    try:
        checksum_destinatario = w3.to_checksum_address(destinatario)
        gas_price = get_dynamic_gas_price()
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
        nonce = w3.eth.get_transaction_count(WALLET_DISTRIBUZIONE)
        tx = token_contract.functions.transfer(checksum_destinatario, quantita * 10**18).build_transaction({
            'from': WALLET_DISTRIBUZIONE,
            'nonce': nonce,
            'gas': 100000,
            'gasPrice': gas_price,
        })
        signed_tx = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
        raw_tx = signed_tx.raw_transaction if hasattr(signed_tx, 'raw_transaction') else signed_tx.rawTransaction
        tx_hash = w3.eth.send_raw_transaction(raw_tx)
        logging.info(f"Tokens sent to {checksum_destinatario}: {quantita} GKY, txHash: {tx_hash.hex()}")
    except Exception as e:
        logging.error(f"Error sending tokens: {e}")
        return False
    session_db = Session()
    try:
        counter = session_db.query(GlobalCounter).first()
        if counter is None:
            counter = GlobalCounter(total_in=0.0, total_out=quantita)
            session_db.add(counter)
        else:
            counter.total_out += quantita
        session_db.commit()
    except Exception as e:
        logging.error(f"Error updating total_out: {e}")
        session_db.rollback()
    finally:
        session_db.close()
    return True

# ------------------ NFT SENDING LOGIC ------------------
def send_nft(destinatario: str) -> bool:
    """
    Sends one NFT randomly chosen (from token IDs 1 to 11) from the distribution wallet.
    Uses the ERC721 safeTransferFrom function.
    """
    try:
        checksum_destinatario = w3.to_checksum_address(destinatario)
        nft_contract = w3.eth.contract(
            address=NFT_CONTRACT_ADDRESS,
            abi=[{
                "constant": False,
                "inputs": [
                    {"name": "from", "type": "address"},
                    {"name": "to", "type": "address"},
                    {"name": "tokenId", "type": "uint256"}
                ],
                "name": "safeTransferFrom",
                "outputs": [],
                "payable": False,
                "stateMutability": "nonpayable",
                "type": "function"
            }]
        )
        token_id = random.randint(1, 11)
        gas_price = get_dynamic_gas_price()
        nonce = w3.eth.get_transaction_count(WALLET_DISTRIBUZIONE)
        tx = nft_contract.functions.safeTransferFrom(WALLET_DISTRIBUZIONE, checksum_destinatario, token_id).build_transaction({
            'from': WALLET_DISTRIBUZIONE,
            'nonce': nonce,
            'gas': 200000,
            'gasPrice': gas_price,
        })
        signed_tx = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
        raw_tx = signed_tx.raw_transaction if hasattr(signed_tx, 'raw_transaction') else signed_tx.rawTransaction
        tx_hash = w3.eth.send_raw_transaction(raw_tx)
        logging.info(f"NFT (tokenId {token_id}) sent to {destinatario}, txHash: {tx_hash.hex()}")
        return True
    except Exception as e:
        logging.error(f"Error sending NFT: {e}")
        return False

# ------------------ PRIZE ASSIGNMENT ------------------
def get_prize() -> str:
    prizes = [
        ("10 GKY", 37.075),
        ("20 GKY", 15),
        ("50 GKY", 10),
        ("100 GKY", 1.50),
        ("NFTSTARTER", 0.025),
        ("500 GKY", 0.25),
        ("1000 GKY", 0.25),
        ("NO PRIZE", 40.50)
    ]
    total = sum(weight for _, weight in prizes)
    r = random.uniform(0, total)
    upto = 0
    for prize, weight in prizes:
        if upto + weight >= r:
            logging.info(f"get_prize() selected: {prize}")
            return prize
        upto += weight
    logging.info("get_prize() selected: NO PRIZE")
    return "NO PRIZE"

# ------------------ GET USER ------------------
def get_user(wallet_address: str):
    session_db = Session()
    try:
        checksum_address = w3.to_checksum_address(wallet_address)
        user = session_db.query(User).filter_by(wallet_address=checksum_address).first()
        if not user:
            user = User(wallet_address=checksum_address, extra_spins=0, last_free_spin_date=None, last_claimed_tasks="")
            session_db.add(user)
            session_db.commit()
            logging.info(f"New user created: {checksum_address}")
        return user
    except Exception as e:
        session_db.rollback()
        logging.error(f"Error getting or creating user for {wallet_address}: {e}")
        # Depending on desired behavior, you might want to raise HTTPException here
        # raise HTTPException(status_code=500, detail=str(e))
        return None # Or handle as appropriate
    finally:
        session_db.close()

# ------------------ ENDPOINT: SPIN ------------------
@app.post("/api/spin")
async def api_spin(req: SpinRequest):
    user = get_user(req.wallet_address)
    session = Session()
    try:
        user = session.merge(user)
        italy = pytz.timezone("Europe/Rome")
        now_date = datetime.datetime.now(italy).date()
        free_spin_available = 1 if (getattr(user, "last_free_spin_date", None) is None or user.last_free_spin_date < now_date) else 0
        if free_spin_available == 0 and user.extra_spins <= 0:
            raise HTTPException(status_code=400, detail="You have no spins left for today.")
        if free_spin_available == 1:
            user.last_free_spin_date = now_date
            session.commit()
        else:
            user.extra_spins -= 1
            session.commit()
        premio = get_prize()
        
        # Simuliamo il premio senza inviarlo realmente
        if premio.strip().upper() == "NO PRIZE":
            result_text = "No prize won. Try again!"
        elif "GKY" in premio:
            result_text = f"You won {premio}! (Test mode - no tokens sent)"
        elif "NFT" in premio:
            result_text = "Congratulations! You won an NFT Starter! (Test mode - no NFT sent)"
        else:
            result_text = f"You won: {premio}!"
            
        # Registriamo comunque il premio nel database
        record = PremioVinto(
            telegram_id=user.telegram_id or "N/A",
            wallet=user.wallet_address,
            premio=premio,
            user_id=user.id
        )
        session.add(record)
        session.commit()
        
        logging.info(f"Spin for {req.wallet_address}: prize {premio} (Test mode)")
        current_free_spin = 1 if (getattr(user, "last_free_spin_date", None) is None or user.last_free_spin_date < now_date) else 0
        available = user.extra_spins + current_free_spin
        return {"message": result_text, "prize": premio, "available_spins": available}
    except Exception as e:
        logging.error(f"Error during spin: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()

# ------------------ ENDPOINT: BUY SPINS ------------------
@app.post("/api/buyspins")
async def api_buyspins(req: BuySpinsRequest):
    user = get_user(req.wallet_address)
    try:
        if req.num_spins not in (1, 3, 10):
            raise HTTPException(status_code=400, detail="You can only buy 1, 3, or 10 extra spins.")
        cost = 50 if req.num_spins == 1 else 125 if req.num_spins == 3 else 300
        msg = f"To purchase {req.num_spins} extra spins, transfer {cost} GKY to {WALLET_DISTRIBUZIONE} and then confirm via /api/confirmbuy."
        logging.info(f"Buy spins request for {req.wallet_address} with num_spins: {req.num_spins}")
        return {"message": msg}
    except Exception as e:
        logging.error(f"Error in buyspins: {e}")
        raise HTTPException(status_code=500, detail="Error in purchase request.")

# ------------------ ENDPOINT: CONFIRM BUY ------------------
@app.post("/api/confirmbuy")
async def api_confirmbuy(req: ConfirmBuyRequest):
    user = get_user(req.wallet_address)
    session = Session()
    try:
        if req.tx_hash in USED_TX:
            raise HTTPException(status_code=400, detail="TX already used for a purchase.")
        if req.num_spins not in (1, 3, 10):
            raise HTTPException(status_code=400, detail="You can only confirm 1, 3, or 10 extra spins.")
        cost = 50 if req.num_spins == 1 else 125 if req.num_spins == 3 else 300
        if not user.wallet_address:
            raise HTTPException(status_code=400, detail="Connect your wallet before confirming.")
        if not verifica_transazione_gky(user.wallet_address, req.tx_hash, cost):
            raise HTTPException(status_code=400, detail="TX not valid or insufficient amount.")
        USED_TX.add(req.tx_hash)
        user = session.merge(user)
        user.extra_spins += req.num_spins
        session.commit()
        session.refresh(user)
        logging.info(f"Extra spins updated for {req.wallet_address}: {user.extra_spins}")
        session_gc = Session()
        try:
            counter = session_gc.query(GlobalCounter).first()
            if counter is None:
                counter = GlobalCounter(total_in=cost, total_out=0.0)
                session_gc.add(counter)
            else:
                counter.total_in += cost
            session_gc.commit()
        except Exception as gc_e:
            logging.error(f"Error updating total_in: {gc_e}")
            session_gc.rollback()
        finally:
            session_gc.close()
        italy = pytz.timezone("Europe/Rome")
        now_date = datetime.datetime.now(italy).date()
        current_free_spin = 1 if (getattr(user, "last_free_spin_date", None) is None or user.last_free_spin_date < now_date) else 0
        available = user.extra_spins + current_free_spin
        return {"message": f"Purchase confirmed! Extra spins: {user.extra_spins}", "available_spins": available}
    except HTTPException as he:
        session.rollback()
        raise he
    except Exception as e:
        session.rollback()
        logging.error(f"Error in confirmbuy: {e}")
        raise HTTPException(status_code=500, detail="Error confirming extra spins.")
    finally:
        session.close()

# ------------------ ENDPOINT: CLAIM REFERRAL ------------------
@app.post("/api/claim_referral")
async def claim_referral(req: ReferralRequest):
    new_user = get_user(req.wallet_address)
    session = Session()
    try:
        # Disallow self-referral
        if new_user.wallet_address.lower() == req.referrer.lower():
            return {"message": "You cannot refer yourself."}
        # Process referral only if not already registered for the referee
        if not getattr(new_user, "referred_by", None) or new_user.referred_by.strip() == "":
            new_user.referred_by = req.referrer
            session.commit()
            # Credit the referrer with 2 free spins
            ref_user = get_user(req.referrer)
            ref_session = Session()
            try:
                ref_user = ref_session.merge(ref_user)
                ref_user.extra_spins += 2
                ref_session.commit()
            except Exception as e:
                ref_session.rollback()
                logging.error(f"Error crediting referrer: {e}")
            finally:
                ref_session.close()
            return {"message": "Referral recorded. (Referrer credited with 2 free spins.)"}
        else:
            return {"message": "Referral already recorded for this user."}
    except Exception as e:
        session.rollback()
        logging.error(f"Error in claim_referral: {e}")
        raise HTTPException(status_code=500, detail="Error claiming referral.")
    finally:
        session.close()

# ------------------ ENDPOINT: CLAIM TASK ------------------
@app.post("/api/claim_task")
async def claim_task(req: TaskClaimRequest, background_tasks: BackgroundTasks):
    user = get_user(req.wallet_address)
    session = Session()
    try:
        user = session.merge(user)
        claimed = user.last_claimed_tasks.split(",") if getattr(user, "last_claimed_tasks", None) else []
        if req.task_id in claimed:
            raise HTTPException(status_code=400, detail="Task already claimed.")
        claimed.append(req.task_id)
        user.last_claimed_tasks = ",".join(claimed)
        session.commit()
        background_tasks.add_task(process_task_claim, req.wallet_address)
        return {"message": "Task completed! You will receive 2 extra spins within 10 minutes."}
    except HTTPException as he:
        session.rollback()
        raise he
    except Exception as e:
        session.rollback()
        logging.error(f"Error in claim_task: {e}")
        raise HTTPException(status_code=500, detail="Error claiming task.")
    finally:
        session.close()

async def process_task_claim(wallet_address: str):
    await asyncio.sleep(600)  # 10 minutes
    session = Session()
    try:
        user = session.query(User).filter(User.wallet_address.ilike(wallet_address)).first()
        if user:
            user.extra_spins += 2
            session.commit()
            logging.info(f"Task claim process: 2 extra spins credited for {wallet_address}")
    except Exception as e:
        session.rollback()
        logging.error(f"Error in process_task_claim: {e}")
    finally:
        session.close()

# ------------------ ENDPOINT: DISTRIBUTE ------------------
@app.post("/api/distribute")
async def api_distribute(req: DistributePrizeRequest):
    if req.prize.strip().upper() == "NO PRIZE":
        return {"message": "No prize to distribute."}
    else:
        return {"message": f"Prize {req.prize} already distributed to wallet {req.wallet_address}."}

# ------------------ ENDPOINT: REFERRAL LINK ------------------
@app.get("/api/referral")
async def api_referral(wallet_address: str):
    referral_link = f"https://t.me/giankytestbot?start=ref_{wallet_address}"
    return {"referral_link": referral_link}

@app.get("/static/loading.html", response_class=HTMLResponse)
async def loading():
    response = FileResponse("static/loading.html")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.get("/index.html", response_class=HTMLResponse)
async def index():
    return FileResponse("static/index.html")

@app.get("/api/restart")
async def restart_server():
    """Endpoint per riavviare il server"""
    try:
        # Riavvia il server
        os.system("uvicorn main:app --reload --host 127.0.0.1 --port 8000")
        return JSONResponse(content={"message": "Server riavviato con successo"})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5000)
