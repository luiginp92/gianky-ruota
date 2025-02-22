from sqlalchemy import Column, Integer, String, DateTime, create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import datetime

# ✅ Configura il database
DATABASE_URL = "sqlite:///database.db"  # Per ambiente di sviluppo; in produzione valuta PostgreSQL/MySQL
engine = create_engine(DATABASE_URL, echo=True)  # Imposta echo=False in produzione
Session = sessionmaker(bind=engine)
Base = declarative_base()

# ✅ Modello per gli utenti
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(String, unique=True, nullable=False)
    wallet_address = Column(String, nullable=True)
    last_play_date = Column(DateTime, nullable=True)
    extra_spins = Column(Integer, default=0)  # Campo per memorizzare i giri extra

# ✅ Modello per registrare i premi vinti
class PremioVinto(Base):
    __tablename__ = "premi_vinti"
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(String, nullable=False)
    wallet = Column(String, nullable=False)
    premio = Column(String, nullable=False)
    data_vincita = Column(DateTime, default=datetime.datetime.utcnow)

# ✅ Crea le tabelle se non esistono
Base.metadata.create_all(engine)
