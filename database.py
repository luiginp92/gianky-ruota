from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import logging

DATABASE_URL = "sqlite:///./giankycoin.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, unique=True, index=True, nullable=True)
    wallet_address = Column(String, unique=True, index=True, nullable=False)
    extra_spins = Column(Integer, default=0)
    referred_by = Column(String, nullable=True)
    last_play_date = Column(DateTime, nullable=True)
    last_share_task = Column(DateTime, nullable=True)
    nonce = Column(String, nullable=True)

class PremioVinto(Base):
    __tablename__ = "premi_vinti"
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, index=True, nullable=False)
    wallet = Column(String, nullable=False)
    premio = Column(String, nullable=False)
    user_id = Column(Integer, nullable=False)
    timestamp = Column(DateTime, server_default=func.now())

class GlobalCounter(Base):
    __tablename__ = "global_counter"
    id = Column(Integer, primary_key=True, index=True)
    total_in = Column(Float, default=0.0)
    total_out = Column(Float, default=0.0)

def init_db():
    try:
        # Crea le tabelle se non esistono già (IF NOT EXISTS)
        Base.metadata.create_all(bind=engine, checkfirst=True)
    except Exception as e:
        logging.warning("init_db() warning: " + str(e))

def Session():
    return SessionLocal()
