from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Az adatbázis fájl helye és neve a mappádon belül
SQLALCHEMY_DATABASE_URL = "sqlite:///./yoga_app.db"

# Az "engine" a tényleges motor, ami végrehajtja az SQL parancsokat
# A check_same_thread=False beállítás kifejezetten a FastAPI és a SQLite közös használatához kell
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# Ez hozza létre a nyitott csatornákat (session) az adatbázis felé, amin az adatok közlekednek
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Ebből az alaposztályból származtattuk a táblákat a models.py-ban (User, YogaClass, Booking)
Base = declarative_base()