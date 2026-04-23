from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base

import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./rfq_agent.db")

# Railway Postgres typically provides postgresql:// but sqlalchemy needs postgresql+psycopg2:// or similarly dialect specifier.
# SQLAlchemy 2.0+ handles `postgresql://` fine with psycopg2 if installed, but if the URL is `postgres://` we need to fix it.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# If it's a sqlite database, we need `check_same_thread: False`, for postgres we do not.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
