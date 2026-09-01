from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timedelta
from database import engine, SessionLocal, Base
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
import models
import secrets

# Táblák létrehozása, ha még nem léteznek
Base.metadata.create_all(bind=engine)


def migrate_yoga_class_columns():
    """Meglévő SQLite adatbázis esetén biztonságosan hozzáadja az új oszlopokat."""
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("yoga_classes")}

    with engine.begin() as connection:
        if "instructor" not in columns:
            connection.execute(text("ALTER TABLE yoga_classes ADD COLUMN instructor VARCHAR"))
        if "note" not in columns:
            connection.execute(text("ALTER TABLE yoga_classes ADD COLUMN note VARCHAR"))
        if "zoom_available" not in columns:
            connection.execute(text("ALTER TABLE yoga_classes ADD COLUMN zoom_available BOOLEAN NOT NULL DEFAULT 0"))


def initialize_existing_class_metadata():
    """A meglévő órákat a hét napja és kezdési ideje alapján ellátja az új adatokkal."""
    db = SessionLocal()
    try:
        classes = db.query(models.YogaClass).all()
        for yoga_class in classes:
            start = yoga_class.start_time
            if not start:
                continue

            weekday = start.weekday()  # hétfő = 0
            time = start.strftime("%H:%M")
            title_lower = (yoga_class.title or "").lower()
            is_breathing = "légzés" in title_lower or "legzes" in title_lower

            instructor = None
            zoom = False
            note = None

            if weekday == 0:  # Hétfő
                if time == "08:15":
                    instructor, zoom = "Klára", True
                elif time == "17:00":
                    instructor, zoom, note = "Klára", True, "Szükséges otthoni kötélfal!"
                elif time == "18:45":
                    instructor, zoom = "Mio", True

            elif weekday == 1:  # Kedd
                zoom = True
                if not is_breathing:
                    instructor = "Klára"

            elif weekday == 2:  # Szerda
                if time == "08:45":
                    instructor, zoom = "Klára", True
                elif time == "17:00":
                    instructor, zoom = "Mio", True

            elif weekday == 3:  # Csütörtök
                zoom = True
                if time == "10:00":
                    note = "Szükséges otthoni kötélfal!"
                elif not is_breathing:
                    instructor = "Klára"

            elif weekday == 4:  # Péntek
                if time == "08:15":
                    instructor, zoom = "Klára", True
                elif time == "15:00":
                    instructor = "Timi"

            # Csak a kért napokon/órákon állítjuk be az adatokat.
            if weekday in (0, 1, 2, 3, 4):
                yoga_class.instructor = instructor
                yoga_class.note = note
                yoga_class.zoom_available = zoom

        db.commit()
    finally:
        db.close()


migrate_yoga_class_columns()
initialize_existing_class_metadata()

app = FastAPI(title="Jóga Foglalási Rendszer")

# CORS engedélyezése
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
security = HTTPBasic()

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "titkosjelszo123"


def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Hibás felhasználónév vagy jelszó",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- PYDANTIC SÉMÁK ---
class UserCreate(BaseModel):
    name: str
    email: str


class ClassCreate(BaseModel):
    title: str
    start_time: datetime
    max_capacity: int = 15
    instructor: str | None = None
    note: str | None = None
    zoom_available: bool = False


class BookingRequest(BaseModel):
    name: str
    email: str
    class_id: int


# --- API VÉGPONTOK ---
@app.get("/")
def read_root():
    return {"message": "A jóga foglalási rendszer backendje sikeresen elindult!"}


@app.post("/classes/")
def create_class(yoga_class: ClassCreate, db: Session = Depends(get_db), admin: str = Depends(verify_admin)):
    new_class = models.YogaClass(
        title=yoga_class.title,
        start_time=yoga_class.start_time,
        max_capacity=yoga_class.max_capacity,
        instructor=yoga_class.instructor,
        note=yoga_class.note,
        zoom_available=yoga_class.zoom_available,
    )
    db.add(new_class)
    db.commit()
    db.refresh(new_class)
    return new_class


@app.get("/classes/")
def read_classes(db: Session = Depends(get_db)):
    classes = db.query(models.YogaClass).all()
    result = []
    for c in classes:
        booked_count = db.query(models.Booking).filter(
            models.Booking.class_id == c.id,
            models.Booking.status == "active"
        ).count()
        free_spots = max(0, c.max_capacity - booked_count)

        end_time = None
        if c.start_time and c.start_time.strftime("%H:%M") == "06:20":
            end_time = c.start_time + timedelta(minutes=30)

        result.append({
            "id": c.id,
            "title": c.title,
            "start_time": c.start_time,
            "end_time": end_time,
            "free_spots": free_spots,
            "instructor": c.instructor,
            "note": c.note,
            "zoom_available": bool(c.zoom_available),
        })
    return result


@app.post("/bookings/")
def create_booking(booking: BookingRequest, db: Session = Depends(get_db)):
    yoga_class = db.query(models.YogaClass).filter(models.YogaClass.id == booking.class_id).first()
    if not yoga_class:
        raise HTTPException(status_code=404, detail="A jógaóra nem található.")

    now = datetime.utcnow()
    time_until_class = yoga_class.start_time - now
    if time_until_class < timedelta(minutes=45):
        raise HTTPException(status_code=400, detail="Erre az órára a jelentkezés már lezárult (45 perccel kezdés előtt).")

    user = db.query(models.User).filter(models.User.email == booking.email).first()
    if not user:
        user = models.User(name=booking.name, email=booking.email)
        db.add(user)
        db.commit()
        db.refresh(user)

    existing_booking = db.query(models.Booking).filter(
        models.Booking.class_id == booking.class_id,
        models.Booking.user_id == user.id,
        models.Booking.status.in_(["active", "waitlisted"])
    ).first()
    if existing_booking:
        raise HTTPException(status_code=400, detail="Már jelentkeztél erre az órára (vagy rajta vagy a várólistán).")

    current_active = db.query(models.Booking).filter(
        models.Booking.class_id == booking.class_id,
        models.Booking.status == "active"
    ).count()

    booking_status = "active"
    if current_active >= yoga_class.max_capacity:
        booking_status = "waitlisted"

    new_booking = models.Booking(
        user_id=user.id,
        class_id=booking.class_id,
        status=booking_status
    )
    db.add(new_booking)
    db.commit()

    if booking_status == "waitlisted":
        return {"message": "A létszám betelt, felkerültél a várólistára!", "status": booking_status}

    return {"message": "Sikeres foglalás!", "status": booking_status}


@app.get("/cancel/{token}")
def cancel_booking(token: str, db: Session = Depends(get_db)):
    booking = db.query(models.Booking).filter(models.Booking.cancel_token == token).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Érvénytelen lemondó link.")

    if booking.status == "cancelled":
        return {"message": "Ezt a foglalást már korábban lemondták."}

    yoga_class = booking.yoga_class
    now = datetime.utcnow()
    time_until_class = yoga_class.start_time - now

    if time_until_class < timedelta(hours=12):
        raise HTTPException(status_code=400, detail="Az órát már nem lehet lemondani, kevesebb mint 12 óra van hátra a kezdésig.")

    was_active = booking.status == "active"
    booking.status = "cancelled"
    db.commit()

    if was_active:
        first_waitlisted = db.query(models.Booking).filter(
            models.Booking.class_id == yoga_class.id,
            models.Booking.status == "waitlisted"
        ).order_by(models.Booking.booking_time.asc()).first()

        if first_waitlisted:
            first_waitlisted.status = "active"
            db.commit()

    return {"message": "A foglalást sikeresen lemondtad."}


@app.get("/classes/{class_id}/bookings/")
def get_class_bookings(class_id: int, db: Session = Depends(get_db), admin: str = Depends(verify_admin)):
    bookings = db.query(models.Booking).filter(
        models.Booking.class_id == class_id,
        models.Booking.status.in_(["active", "waitlisted"])
    ).order_by(models.Booking.booking_time.asc()).all()

    result = []
    for b in bookings:
        user = db.query(models.User).filter(models.User.id == b.user_id).first()
        if user:
            result.append({
                "id": b.id,
                "name": user.name,
                "email": user.email,
                "status": b.status
            })
    return result


@app.delete("/admin/bookings/{booking_id}")
def admin_remove_booking(booking_id: int, db: Session = Depends(get_db), admin: str = Depends(verify_admin)):
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Foglalás nem található.")

    if booking.status == "cancelled":
        return {"message": "Már le van mondva."}

    was_active = booking.status == "active"
    booking.status = "cancelled"
    yoga_class = booking.yoga_class
    db.commit()

    if was_active:
        first_waitlisted = db.query(models.Booking).filter(
            models.Booking.class_id == yoga_class.id,
            models.Booking.status == "waitlisted"
        ).order_by(models.Booking.booking_time.asc()).first()

        if first_waitlisted:
            first_waitlisted.status = "active"
            db.commit()

    return {"message": "Tanítvány sikeresen eltávolítva."}


@app.delete("/admin/classes/{class_id}")
def delete_class(class_id: int, db: Session = Depends(get_db), admin: str = Depends(verify_admin)):
    yoga_class = db.query(models.YogaClass).filter(models.YogaClass.id == class_id).first()
    if not yoga_class:
        raise HTTPException(status_code=404, detail="Az óra nem található.")

    db.query(models.Booking).filter(models.Booking.class_id == class_id).delete()
    db.delete(yoga_class)
    db.commit()

    return {"message": "A jógaóra és a jelentkezések sikeresen törölve."}


@app.get("/admin/verify")
def verify_login(admin: str = Depends(verify_admin)):
    return {"message": "Sikeres belépés"}
