import os
import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# URL database dalle variabili d'ambiente (per Heroku, DATABASE_URL è fornito automaticamente).
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")

# Crea engine SQLAlchemy
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Modello Utente
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, nullable=True)
    wallet_address = Column(String, unique=True, index=True, nullable=False)
    extra_spins = Column(Integer, default=0)         # giri extra acquistati/non ancora usati
    referred_by = Column(String, nullable=True)      # indirizzo wallet di chi lo ha referenziato (se applicabile)
    last_play_date = Column(DateTime, nullable=True)   # data ultimo giro (per calcolo free daily spin)
    last_share_task = Column(DateTime, nullable=True)  # data ultima completione task condivisione
    nonce = Column(String, nullable=True)              # nonce temporaneo per login (una volta)

# Modello Premio Vinto
class PremioVinto(Base):
    __tablename__ = "premi_vinti"
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, nullable=True)
    wallet = Column(String, nullable=False)
    premio = Column(String, nullable=False)
    user_id = Column(Integer, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

# Modello Global Counter
class GlobalCounter(Base):
    __tablename__ = "global_counter"
    id = Column(Integer, primary_key=True, index=True)
    total_in = Column(Float, default=0.0)   # totale GKY ricevuti (acquisti)
    total_out = Column(Float, default=0.0)  # totale GKY inviati (premi)

def init_db():
    # Crea le tabelle nel database se non esistono
    Base.metadata.create_all(bind=engine)
    # Inizializza GlobalCounter se non esiste
    with Session() as session:
        if session.query(GlobalCounter).first() is None:
            counter = GlobalCounter(total_in=0.0, total_out=0.0)
            session.add(counter)
            session.commit()
