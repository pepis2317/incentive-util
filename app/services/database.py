import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

DB_PATH = os.environ.get("DB_PATH", "./data/incentive-util.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(bind=engine,autoflush=False)