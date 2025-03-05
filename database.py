import os
import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Se non è impostata la variabile DATABASE_URL, usa SQLite in locale
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
Session = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, nullable=True)
    wallet_address = Column(String, unique=True, index=True, nullable=False)
    extra_spins = Column(Integer, default=0)
    referred_by = Column(String, nullable=True)
    last_play_date = Column(DateTime, nullable=True)
    last_share_task = Column(DateTime, nullable=True)
    nonce = Column(String, nullable=True)

class PremioVinto(Base):
    __tablename__ = "premi_vinti"
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, nullable=True)
    wallet = Column(String, nullable=False)
    premio = Column(String, nullable=False)
    user_id = Column(Integer, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

class GlobalCounter(Base):
    __tablename__ = "global_counter"
    id = Column(Integer, primary_key=True, index=True)
    total_in = Column(Float, default=0.0)
    total_out = Column(Float, default=0.0)

def init_db():
    # Crea le tabelle se non esistono
    Base.metadata.create_all(bind=engine)
