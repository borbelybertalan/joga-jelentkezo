from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import BASE_DIR
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
database_path = Path(os.getenv("DATABASE_PATH", BASE_DIR / "yoga_app.db")).resolve()
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL", f"sqlite:///{database_path.as_posix()}"
)

# SQLite-nál minden kapcsolaton külön engedélyezni kell az idegen kulcsokat.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 10},
)


@event.listens_for(engine, "connect")
def configure_sqlite_connection(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=10000")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass
