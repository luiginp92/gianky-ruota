from sqlalchemy import Column, Integer, String, DateTime, Float, create_engine, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
import datetime

# Configura il database
DATABASE_URL = "sqlite:///database.db"  # Per ambiente di sviluppo; in produzione valuta PostgreSQL/MySQL
engine = create_engine(DATABASE_URL, echo=True)  # Imposta echo=False in produzione
Session = sessionmaker(bind=engine)
Base = declarative_base()

# Modello per gli utenti
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(String, unique=True, nullable=False, index=True)  # ID Telegram univoco
    wallet_address = Column(String, nullable=True)  # Indirizzo del wallet collegato
    last_play_date = Column(DateTime, nullable=True)  # Data dell'ultimo giro effettuato
    extra_spins = Column(Integer, default=0)  # Numero di spin extra acquistati
    last_share_task = Column(DateTime, nullable=True)  # Data dell'ultima task di condivisione completata
    referred_by = Column(String, nullable=True)  # ID Telegram dell'utente invitante (referral)

    # Relazione: un utente può avere molti premi vinti
    premi_vinti = relationship("PremioVinto", back_populates="user", cascade="all, delete-orphan")

# Modello per registrare i premi vinti
class PremioVinto(Base):
    __tablename__ = "premi_vinti"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # Riferimento all'utente
    telegram_id = Column(String, nullable=False)  # ID Telegram dell'utente
    wallet = Column(String, nullable=False)         # Wallet a cui il premio è stato accreditato
    premio = Column(String, nullable=False)         # Descrizione del premio vinto
    tx_hash = Column(String, nullable=True)         # Riferimento alla transazione (tx hash)
    data_vincita = Column(DateTime, default=datetime.datetime.utcnow)  # Data e ora del premio

    # Relazione: collega il premio all'utente
    user = relationship("User", back_populates="premi_vinti")

# Tabella per il contatore globale di GKY
class GlobalCounter(Base):
    __tablename__ = "global_counter"
    id = Column(Integer, primary_key=True, autoincrement=True)
    total_in = Column(Float, default=0.0)   # Totale token in entrata (pagamenti ricevuti)
    total_out = Column(Float, default=0.0)  # Totale token in uscita (premi inviati)

# Crea le tabelle se non esistono
Base.metadata.create_all(engine)
