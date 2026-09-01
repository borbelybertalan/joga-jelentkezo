import re
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from auth import create_admin_token, verify_admin, verify_password
from config import BASE_DIR, csv_environment
from database import SessionLocal
from migrations import run_migrations
import models
from time_utils import to_utc_naive, utc_now_naive, utc_to_local


run_migrations()

app = FastAPI(title="Jóga Foglalási Rendszer")
allowed_origins = csv_environment("FRONTEND_ORIGINS")
if allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; connect-src 'self'; base-uri 'self'; form-action 'self'; "
        "frame-ancestors 'none'"
    )
    if request.url.path == "/cancel.html" or request.url.path.startswith("/bookings/cancel/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AdminLogin(StrictModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=512)


class ClassCreate(StrictModel):
    title: str = Field(min_length=1, max_length=160)
    start_time: datetime
    max_capacity: int = Field(default=15, ge=1, le=200)
    instructor: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=500)
    zoom_available: bool = False

    @field_validator("start_time")
    @classmethod
    def normalise_start_time(cls, value: datetime) -> datetime:
        return to_utc_naive(value)


class BookingRequest(StrictModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    class_id: int = Field(ge=1)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalised = value.casefold()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalised):
            raise ValueError("Érvényes e-mail címet adj meg.")
        return normalised


LOGIN_ATTEMPTS: dict[str, list[float]] = defaultdict(list)
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 15 * 60


def _check_login_rate_limit(client_key: str) -> None:
    now = time.monotonic()
    attempts = LOGIN_ATTEMPTS[client_key]
    attempts[:] = [attempt for attempt in attempts if now - attempt < LOGIN_WINDOW_SECONDS]
    if len(attempts) >= MAX_LOGIN_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Túl sok sikertelen belépési kísérlet. Próbáld újra később.",
        )


def _class_payload(yoga_class: models.YogaClass, booked_count: int) -> dict:
    local_start = utc_to_local(yoga_class.start_time)
    end_time = local_start + timedelta(minutes=30) if local_start.strftime("%H:%M") == "06:20" else None
    return {
        "id": yoga_class.id,
        "title": yoga_class.title,
        "start_time": local_start,
        "end_time": end_time,
        "free_spots": max(0, yoga_class.max_capacity - booked_count),
        "instructor": yoga_class.instructor,
        "note": yoga_class.note,
        "zoom_available": bool(yoga_class.zoom_available),
    }


def _begin_write_transaction(db: Session) -> None:
    # SQLite-nál ez sorba rendezi az író kéréseket, hogy a kapacitás-számítás és a mentés atomi legyen.
    db.execute(text("BEGIN IMMEDIATE"))


def _cancel_booking_in_transaction(
    db: Session, booking: models.Booking, *, respect_deadline: bool
) -> dict:
    yoga_class = booking.yoga_class
    if booking.status == "cancelled":
        return {"message": "Ez a foglalás már korábban le lett mondva.", "already_cancelled": True}

    if respect_deadline and yoga_class.start_time - utc_now_naive() < timedelta(hours=12):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Az órát már nem lehet lemondani, kevesebb mint 12 óra van hátra.",
        )

    was_active = booking.status == "active"
    booking.status = "cancelled"

    if was_active:
        first_waitlisted = (
            db.query(models.Booking)
            .filter(
                models.Booking.class_id == yoga_class.id,
                models.Booking.status == "waitlisted",
            )
            .order_by(models.Booking.booking_time.asc())
            .first()
        )
        if first_waitlisted:
            first_waitlisted.status = "active"

    return {"message": "A foglalást sikeresen lemondtad.", "already_cancelled": False}


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/admin/login")
def login(credentials: AdminLogin, request: Request):
    client_key = request.client.host if request.client else "unknown"
    _check_login_rate_limit(client_key)
    if not verify_password(credentials.username, credentials.password):
        LOGIN_ATTEMPTS[client_key].append(time.monotonic())
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Hibás belépési adatok.")

    LOGIN_ATTEMPTS.pop(client_key, None)
    access_token, expires_at = create_admin_token(credentials.username)
    return {"access_token": access_token, "token_type": "bearer", "expires_at": expires_at}


@app.get("/admin/verify")
def verify_login(admin: str = Depends(verify_admin)):
    return {"message": "Sikeres belépés", "username": admin}


@app.post("/classes/", status_code=status.HTTP_201_CREATED)
def create_class(
    yoga_class: ClassCreate,
    db: Session = Depends(get_db),
    admin: str = Depends(verify_admin),
):
    new_class = models.YogaClass(
        title=yoga_class.title,
        start_time=yoga_class.start_time,
        max_capacity=yoga_class.max_capacity,
        instructor=yoga_class.instructor or None,
        note=yoga_class.note or None,
        zoom_available=yoga_class.zoom_available,
    )
    try:
        db.add(new_class)
        db.commit()
        db.refresh(new_class)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Az óra adatai érvénytelenek.")
    return _class_payload(new_class, booked_count=0)


@app.get("/classes/")
def read_classes(db: Session = Depends(get_db)):
    active_counts = dict(
        db.query(models.Booking.class_id, func.count(models.Booking.id))
        .filter(models.Booking.status == "active")
        .group_by(models.Booking.class_id)
        .all()
    )
    classes = db.query(models.YogaClass).order_by(models.YogaClass.start_time.asc()).all()
    return [_class_payload(yoga_class, active_counts.get(yoga_class.id, 0)) for yoga_class in classes]


@app.post("/bookings/", status_code=status.HTTP_201_CREATED)
def create_booking(booking: BookingRequest, request: Request, db: Session = Depends(get_db)):
    try:
        _begin_write_transaction(db)
        yoga_class = db.get(models.YogaClass, booking.class_id)
        if not yoga_class:
            raise HTTPException(status_code=404, detail="A jógaóra nem található.")
        if yoga_class.start_time - utc_now_naive() < timedelta(minutes=45):
            raise HTTPException(
                status_code=400,
                detail="Erre az órára a jelentkezés már lezárult (45 perccel kezdés előtt).",
            )

        user = db.query(models.User).filter(models.User.email == booking.email).first()
        if not user:
            user = models.User(name=booking.name, email=booking.email)
            db.add(user)
            db.flush()

        existing_booking = (
            db.query(models.Booking)
            .filter(
                models.Booking.class_id == yoga_class.id,
                models.Booking.user_id == user.id,
            )
            .first()
        )
        current_active = (
            db.query(models.Booking)
            .filter(
                models.Booking.class_id == yoga_class.id,
                models.Booking.status == "active",
            )
            .count()
        )
        booking_status = "active" if current_active < yoga_class.max_capacity else "waitlisted"

        if existing_booking and existing_booking.status in {"active", "waitlisted"}:
            raise HTTPException(
                status_code=409,
                detail="Már jelentkeztél erre az órára vagy rajta vagy a várólistán.",
            )

        if existing_booking:
            existing_booking.status = booking_status
            existing_booking.booking_time = utc_now_naive()
            existing_booking.cancel_token = secrets.token_urlsafe(32)
            saved_booking = existing_booking
        else:
            saved_booking = models.Booking(user_id=user.id, class_id=yoga_class.id, status=booking_status)
            db.add(saved_booking)
            db.flush()

        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A foglalás ütközött egy másik kéréssel. Próbáld újra.")
    except OperationalError:
        db.rollback()
        raise HTTPException(status_code=503, detail="A foglalási rendszer épp foglalt. Próbáld újra rövidesen.")

    cancel_url = str(request.base_url).rstrip("/") + f"/cancel.html?token={saved_booking.cancel_token}"
    message = (
        "A létszám betelt, felkerültél a várólistára!"
        if booking_status == "waitlisted"
        else "Sikeres foglalás!"
    )
    return {"message": message, "status": booking_status, "cancel_url": cancel_url}


@app.get("/bookings/cancel/{token}")
def get_cancellation_details(token: str, db: Session = Depends(get_db)):
    booking = db.query(models.Booking).filter(models.Booking.cancel_token == token).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Érvénytelen lemondó link.")
    yoga_class = booking.yoga_class
    return {
        "title": yoga_class.title,
        "start_time": utc_to_local(yoga_class.start_time),
        "status": booking.status,
        "can_cancel": booking.status != "cancelled"
        and yoga_class.start_time - utc_now_naive() >= timedelta(hours=12),
    }


@app.post("/bookings/cancel/{token}")
def cancel_booking(token: str, db: Session = Depends(get_db)):
    try:
        _begin_write_transaction(db)
        booking = db.query(models.Booking).filter(models.Booking.cancel_token == token).first()
        if not booking:
            raise HTTPException(status_code=404, detail="Érvénytelen lemondó link.")
        result = _cancel_booking_in_transaction(db, booking, respect_deadline=True)
        db.commit()
        return result
    except HTTPException:
        db.rollback()
        raise
    except OperationalError:
        db.rollback()
        raise HTTPException(status_code=503, detail="A lemondási rendszer épp foglalt. Próbáld újra rövidesen.")


@app.get("/classes/{class_id}/bookings/")
def get_class_bookings(
    class_id: int, db: Session = Depends(get_db), admin: str = Depends(verify_admin)
):
    rows = (
        db.query(models.Booking, models.User)
        .join(models.User, models.Booking.user_id == models.User.id)
        .filter(
            models.Booking.class_id == class_id,
            models.Booking.status.in_(["active", "waitlisted"]),
        )
        .order_by(models.Booking.booking_time.asc())
        .all()
    )
    return [
        {"id": booking.id, "name": user.name, "email": user.email, "status": booking.status}
        for booking, user in rows
    ]


@app.delete("/admin/bookings/{booking_id}")
def admin_remove_booking(
    booking_id: int, db: Session = Depends(get_db), admin: str = Depends(verify_admin)
):
    try:
        _begin_write_transaction(db)
        booking = db.get(models.Booking, booking_id)
        if not booking:
            raise HTTPException(status_code=404, detail="Foglalás nem található.")
        result = _cancel_booking_in_transaction(db, booking, respect_deadline=False)
        db.commit()
        return {
            "message": "Tanítvány sikeresen eltávolítva.",
            "already_cancelled": result["already_cancelled"],
        }
    except HTTPException:
        db.rollback()
        raise
    except OperationalError:
        db.rollback()
        raise HTTPException(status_code=503, detail="A foglalási rendszer épp foglalt. Próbáld újra rövidesen.")


@app.delete("/admin/classes/{class_id}")
def delete_class(
    class_id: int, db: Session = Depends(get_db), admin: str = Depends(verify_admin)
):
    try:
        _begin_write_transaction(db)
        yoga_class = db.get(models.YogaClass, class_id)
        if not yoga_class:
            raise HTTPException(status_code=404, detail="Az óra nem található.")
        db.query(models.Booking).filter(models.Booking.class_id == class_id).delete(
            synchronize_session=False
        )
        db.delete(yoga_class)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Az óra nem törölhető biztonságosan.")
    return {"message": "A jógaóra és a jelentkezések sikeresen törölve."}


# Az API útvonalak után kerül fel, ezért nem takarja el őket; a frontend és a lemondó oldal azonos originről fut.
app.mount("/", StaticFiles(directory=BASE_DIR / "frontend", html=True), name="frontend")
