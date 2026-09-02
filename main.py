import asyncio
import contextlib
import re
import secrets
import time
from collections import defaultdict
from datetime import date, datetime, timedelta

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

import models
from auth import create_admin_token, verify_admin, verify_password
from config import BASE_DIR, csv_environment
from database import SessionLocal
from email_service import send_booking_confirmation
from migrations import run_migrations
from time_utils import to_utc_naive, utc_now_naive, utc_to_local

run_migrations()


async def _pass_settlement_loop() -> None:
    """Óránkénti külső kérés nélkül is rendezi a 12 órás bérletlevonásokat."""
    while True:
        await asyncio.sleep(60)
        db = SessionLocal()
        try:
            _begin_write_transaction(db)
            _settle_due_pass_uses(db)
            db.commit()
        except OperationalError:
            db.rollback()
        finally:
            db.close()


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    settlement_task = asyncio.create_task(_pass_settlement_loop())
    try:
        yield
    finally:
        settlement_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await settlement_task


app = FastAPI(title="Jóga Foglalási Rendszer", lifespan=lifespan)
allowed_origins = csv_environment("FRONTEND_ORIGINS")
if allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
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


class ClassUpdate(ClassCreate):
    """A szerkeszthető óraadatok megegyeznek az új óra kötelező adataival."""


EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def _normalise_email(value: str) -> str:
    normalised = value.casefold()
    if not EMAIL_PATTERN.fullmatch(normalised):
        raise ValueError("Érvényes e-mail címet adj meg.")
    return normalised


class BookingRequest(StrictModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    class_id: int = Field(ge=1)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _normalise_email(value)


class PassGrantRequest(StrictModel):
    pass_type: str = Field(min_length=1, max_length=20)

    @field_validator("pass_type")
    @classmethod
    def validate_pass_type(cls, value: str) -> str:
        if value not in {"monthly", "eight_visit"}:
            raise ValueError("Csak havi vagy 8 alkalmas bérlet adható hozzá.")
        return value


class PassUpdateRequest(StrictModel):
    # A naptári nap végét tekintjük a bérlet lejáratának, így az adminnak
    # csak a vendég számára érthető dátumot kell megadnia.
    valid_until: date
    remaining_uses: int | None = Field(default=None, ge=0, le=8)


class EmailMergeRequest(StrictModel):
    primary_email: str = Field(min_length=3, max_length=254)
    secondary_email: str = Field(min_length=3, max_length=254)

    @field_validator("primary_email", "secondary_email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _normalise_email(value)


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
        "max_capacity": yoga_class.max_capacity,
        "free_spots": max(0, yoga_class.max_capacity - booked_count),
        "instructor": yoga_class.instructor,
        "note": yoga_class.note,
        "zoom_available": bool(yoga_class.zoom_available),
    }


def _find_user_by_email(db: Session, email: str) -> models.User | None:
    user = db.query(models.User).filter(models.User.email == email).first()
    if user:
        return user
    alias = db.query(models.UserEmailAlias).filter(models.UserEmailAlias.email == email).first()
    return alias.user if alias else None


def _is_pass_active(yoga_pass: models.Pass, at: datetime | None = None) -> bool:
    reference_time = at or utc_now_naive()
    if yoga_pass.valid_until < reference_time:
        return False
    return yoga_pass.pass_type == "monthly" or (yoga_pass.remaining_uses or 0) > 0


def _pass_payload(yoga_pass: models.Pass, *, at: datetime | None = None) -> dict:
    return {
        "id": yoga_pass.id,
        "type": yoga_pass.pass_type,
        "active": _is_pass_active(yoga_pass, at),
        "issued_at": utc_to_local(yoga_pass.issued_at),
        "valid_until": utc_to_local(yoga_pass.valid_until),
        "remaining_uses": yoga_pass.remaining_uses,
    }


def _active_passes_for_user(
    db: Session, user_id: int, *, at: datetime | None = None
) -> list[models.Pass]:
    reference_time = at or utc_now_naive()
    passes = (
        db.query(models.Pass)
        .filter(models.Pass.user_id == user_id, models.Pass.valid_until >= reference_time)
        .order_by(models.Pass.issued_at.desc(), models.Pass.id.desc())
        .all()
    )
    return [yoga_pass for yoga_pass in passes if _is_pass_active(yoga_pass, reference_time)]


def _pass_summary_for_user(db: Session, user_id: int) -> dict | None:
    active_passes = _active_passes_for_user(db, user_id)
    if not active_passes:
        return None
    # Az utoljára kiadott, még használható bérlet jelenik meg elsődlegesként.
    return _pass_payload(active_passes[0])


def _pass_for_booking(db: Session, user_id: int, class_start: datetime) -> models.Pass | None:
    active_passes = _active_passes_for_user(db, user_id, at=class_start)
    return active_passes[0] if active_passes else None


def _settle_due_pass_uses(db: Session, now: datetime | None = None) -> None:
    """A 8 alkalmas bérletekből a lemondási határidő elérésekor von le alkalmat."""
    reference_time = now or utc_now_naive()
    deadline = reference_time + timedelta(hours=12)
    due_bookings = (
        db.query(models.Booking)
        .join(models.YogaClass)
        .filter(
            models.Booking.status == "active",
            models.Booking.pass_id.is_not(None),
            models.Booking.pass_usage_settled.is_(False),
            models.YogaClass.start_time <= deadline,
        )
        .all()
    )
    for booking in due_bookings:
        yoga_pass = booking.pass_record
        if yoga_pass and yoga_pass.pass_type == "eight_visit" and (yoga_pass.remaining_uses or 0) > 0:
            yoga_pass.remaining_uses -= 1
            booking.pass_use_consumed = True
        booking.pass_usage_settled = True


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

    if booking.pass_use_consumed and booking.pass_record:
        # Adminos eltávolításnál is visszaadjuk az alkalmat, mert az óra már nem lesz megtartva
        # ennek a foglalásnak a terhére.
        booking.pass_record.remaining_uses = (booking.pass_record.remaining_uses or 0) + 1
        booking.pass_use_consumed = False

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


@app.get("/admin/users/")
def list_users(db: Session = Depends(get_db), admin: str = Depends(verify_admin)):
    users = db.query(models.User).order_by(models.User.name.asc(), models.User.id.asc()).all()
    return [
        {
            "id": user.id,
            "name": user.name,
            "emails": [user.email]
            + [alias.email for alias in sorted(user.email_aliases, key=lambda item: item.email)],
            "active_pass": _pass_summary_for_user(db, user.id),
            "passes": [
                _pass_payload(yoga_pass)
                for yoga_pass in sorted(user.passes, key=lambda item: (item.issued_at, item.id), reverse=True)
            ],
        }
        for user in users
    ]


@app.post("/admin/users/{user_id}/passes/", status_code=status.HTTP_201_CREATED)
def grant_pass(
    user_id: int,
    pass_request: PassGrantRequest,
    db: Session = Depends(get_db),
    admin: str = Depends(verify_admin),
):
    try:
        _begin_write_transaction(db)
        user = db.get(models.User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="A vendég nem található.")
        if _active_passes_for_user(db, user.id):
            raise HTTPException(
                status_code=409,
                detail="Ennek a vendégnek már van aktív bérlete. Előbb módosítsd vagy távolítsd el azt.",
            )
        issued_at = utc_now_naive()
        duration_days = 30 if pass_request.pass_type == "monthly" else 60
        yoga_pass = models.Pass(
            user_id=user.id,
            pass_type=pass_request.pass_type,
            issued_at=issued_at,
            valid_until=issued_at + timedelta(days=duration_days),
            remaining_uses=None if pass_request.pass_type == "monthly" else 8,
        )
        db.add(yoga_pass)
        db.commit()
        db.refresh(yoga_pass)
        return _pass_payload(yoga_pass)
    except HTTPException:
        db.rollback()
        raise
    except OperationalError:
        db.rollback()
        raise HTTPException(status_code=503, detail="A bérletet most nem lehet menteni. Próbáld újra.")


@app.delete("/admin/passes/{pass_id}/")
def delete_pass(
    pass_id: int,
    db: Session = Depends(get_db),
    admin: str = Depends(verify_admin),
):
    try:
        _begin_write_transaction(db)
        yoga_pass = db.get(models.Pass, pass_id)
        if not yoga_pass:
            raise HTTPException(status_code=404, detail="A bérlet nem található.")

        # A foglalási előzmény megmarad, de a törölt bérlethez többé nem kapcsolódik.
        # Így a később esedékes alkalomlevonás sem próbál nem létező bérletet módosítani.
        db.query(models.Booking).filter(models.Booking.pass_id == yoga_pass.id).update(
            {
                models.Booking.pass_id: None,
                models.Booking.pass_use_consumed: False,
                models.Booking.pass_usage_settled: False,
            },
            synchronize_session=False,
        )
        db.delete(yoga_pass)
        db.commit()
        return {"message": "A bérlet sikeresen eltávolítva."}
    except HTTPException:
        db.rollback()
        raise
    except (IntegrityError, OperationalError):
        db.rollback()
        raise HTTPException(status_code=503, detail="A bérletet most nem lehet eltávolítani. Próbáld újra.")


@app.patch("/admin/passes/{pass_id}/")
def update_pass(
    pass_id: int,
    pass_request: PassUpdateRequest,
    db: Session = Depends(get_db),
    admin: str = Depends(verify_admin),
):
    try:
        _begin_write_transaction(db)
        yoga_pass = db.get(models.Pass, pass_id)
        if not yoga_pass:
            raise HTTPException(status_code=404, detail="A bérlet nem található.")

        if yoga_pass.pass_type == "monthly" and pass_request.remaining_uses is not None:
            raise HTTPException(
                status_code=400,
                detail="A havi bérlethez nem tartozik alkalomszám.",
            )
        if yoga_pass.pass_type == "eight_visit" and pass_request.remaining_uses is None:
            raise HTTPException(
                status_code=400,
                detail="A 8 alkalmas bérlet fennmaradó alkalmait is add meg.",
            )

        local_end_of_day = datetime.combine(pass_request.valid_until, datetime.max.time())
        yoga_pass.valid_until = to_utc_naive(local_end_of_day)
        if yoga_pass.pass_type == "eight_visit":
            yoga_pass.remaining_uses = pass_request.remaining_uses
        db.commit()
        db.refresh(yoga_pass)
        return _pass_payload(yoga_pass)
    except HTTPException:
        db.rollback()
        raise
    except OperationalError:
        db.rollback()
        raise HTTPException(status_code=503, detail="A bérletet most nem lehet menteni. Próbáld újra.")


@app.post("/admin/users/merge-emails/")
def merge_user_emails(
    merge_request: EmailMergeRequest,
    db: Session = Depends(get_db),
    admin: str = Depends(verify_admin),
):
    if merge_request.primary_email == merge_request.secondary_email:
        raise HTTPException(status_code=400, detail="Két különböző e-mail-címet adj meg.")

    try:
        _begin_write_transaction(db)
        primary_user = _find_user_by_email(db, merge_request.primary_email)
        if not primary_user:
            raise HTTPException(status_code=404, detail="Az elsődleges e-mailhez nem tartozik vendég.")

        secondary_user = _find_user_by_email(db, merge_request.secondary_email)
        if secondary_user is primary_user:
            db.commit()
            return {"message": "Ez az e-mail-cím már ehhez a vendéghez tartozik."}

        if secondary_user:
            primary_class_ids = [
                class_id
                for (class_id,) in db.query(models.Booking.class_id)
                .filter(models.Booking.user_id == primary_user.id)
                .all()
            ]
            if primary_class_ids and (
                db.query(models.Booking)
                .filter(
                    models.Booking.user_id == secondary_user.id,
                    models.Booking.class_id.in_(primary_class_ids),
                )
                .first()
            ):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "A két vendégnek ugyanarra az órára is van foglalása. "
                        "Előbb rendezd ezt az adminfelületen, majd próbáld újra az összevonást."
                    ),
                )

            if _active_passes_for_user(db, primary_user.id) and _active_passes_for_user(
                db, secondary_user.id
            ):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Mindkét vendéghez aktív bérlet tartozik. "
                        "Az összevonás előtt döntsd el, melyik bérlet maradjon érvényben."
                    ),
                )

            db.query(models.Booking).filter(models.Booking.user_id == secondary_user.id).update(
                {models.Booking.user_id: primary_user.id}, synchronize_session=False
            )
            db.query(models.Pass).filter(models.Pass.user_id == secondary_user.id).update(
                {models.Pass.user_id: primary_user.id}, synchronize_session=False
            )
            db.query(models.UserEmailAlias).filter(
                models.UserEmailAlias.user_id == secondary_user.id
            ).update({models.UserEmailAlias.user_id: primary_user.id}, synchronize_session=False)
            db.add(
                models.UserEmailAlias(user_id=primary_user.id, email=secondary_user.email)
            )
            db.flush()
            db.delete(secondary_user)
        else:
            db.add(
                models.UserEmailAlias(user_id=primary_user.id, email=merge_request.secondary_email)
            )

        db.commit()
        return {"message": "Az e-mail-címek sikeresen össze lettek vonva."}
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Az e-mail-cím összevonása duplikált adatot hozna létre.",
        )
    except OperationalError:
        db.rollback()
        raise HTTPException(status_code=503, detail="Az e-mail-címeket most nem lehet összevonni.")


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


@app.patch("/admin/classes/{class_id}")
def update_class(
    class_id: int,
    class_update: ClassUpdate,
    db: Session = Depends(get_db),
    admin: str = Depends(verify_admin),
):
    try:
        _begin_write_transaction(db)
        yoga_class = db.get(models.YogaClass, class_id)
        if not yoga_class:
            raise HTTPException(status_code=404, detail="Az óra nem található.")

        active_bookings = (
            db.query(models.Booking)
            .filter(models.Booking.class_id == yoga_class.id, models.Booking.status == "active")
            .count()
        )
        if class_update.max_capacity < active_bookings:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"A létszám nem lehet kisebb az {active_bookings} aktív jelentkezőnél. "
                    "Előbb távolíts el jelentkezőt, vagy adj meg nagyobb létszámot."
                ),
            )

        # Az időpont változtatása a 12 órás bérletlevonási határidőt is módosíthatja.
        _settle_due_pass_uses(db)
        old_start_time = yoga_class.start_time
        yoga_class.title = class_update.title
        yoga_class.start_time = class_update.start_time
        yoga_class.max_capacity = class_update.max_capacity
        yoga_class.instructor = class_update.instructor or None
        yoga_class.note = class_update.note or None
        yoga_class.zoom_available = class_update.zoom_available

        if yoga_class.start_time > utc_now_naive() + timedelta(hours=12) and old_start_time != yoga_class.start_time:
            for booking in yoga_class.bookings:
                if booking.status != "active":
                    continue
                if booking.pass_use_consumed and booking.pass_record:
                    booking.pass_record.remaining_uses = (booking.pass_record.remaining_uses or 0) + 1
                    booking.pass_use_consumed = False
                booking.pass_usage_settled = False

        _settle_due_pass_uses(db)
        db.commit()
        db.refresh(yoga_class)
        return _class_payload(yoga_class, booked_count=active_bookings)
    except HTTPException:
        db.rollback()
        raise
    except (IntegrityError, OperationalError):
        db.rollback()
        raise HTTPException(status_code=503, detail="Az óra most nem szerkeszthető. Próbáld újra.")


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
        _settle_due_pass_uses(db)
        yoga_class = db.get(models.YogaClass, booking.class_id)
        if not yoga_class:
            raise HTTPException(status_code=404, detail="A jógaóra nem található.")
        if yoga_class.start_time - utc_now_naive() < timedelta(minutes=45):
            raise HTTPException(
                status_code=400,
                detail="Erre az órára a jelentkezés már lezárult (45 perccel kezdés előtt).",
            )

        user = _find_user_by_email(db, booking.email)
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

        assigned_pass = _pass_for_booking(db, user.id, yoga_class.start_time)
        if existing_booking:
            existing_booking.status = booking_status
            existing_booking.booking_time = utc_now_naive()
            existing_booking.cancel_token = secrets.token_urlsafe(32)
            existing_booking.pass_id = assigned_pass.id if assigned_pass else None
            existing_booking.pass_use_consumed = False
            existing_booking.pass_usage_settled = False
            saved_booking = existing_booking
        else:
            saved_booking = models.Booking(
                user_id=user.id,
                class_id=yoga_class.id,
                status=booking_status,
                pass_id=assigned_pass.id if assigned_pass else None,
            )
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
    payment_notice = None
    if not assigned_pass:
        payment_notice = "Nincs aktív bérleted. A bérletet vagy az egyszeri jegyet személyesen kell rendezned."
        message = f"{message} {payment_notice}"
    email_sent = send_booking_confirmation(
        recipient=booking.email,
        class_title=yoga_class.title,
        class_start=utc_to_local(yoga_class.start_time).strftime("%Y. %m. %d. %H:%M"),
        booking_status=booking_status,
        cancel_url=cancel_url,
        pass_summary=_pass_payload(assigned_pass) if assigned_pass else None,
        payment_notice=payment_notice,
    )
    return {
        "message": message,
        "status": booking_status,
        "cancel_url": cancel_url,
        "pass": _pass_payload(assigned_pass) if assigned_pass else None,
        "payment_notice": payment_notice,
        "email_sent": email_sent,
    }


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
        _settle_due_pass_uses(db)
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
        {
            "id": booking.id,
            "name": user.name,
            "email": user.email,
            "status": booking.status,
            "pass": _pass_summary_for_user(db, user.id),
        }
        for booking, user in rows
    ]


@app.delete("/admin/bookings/{booking_id}")
def admin_remove_booking(
    booking_id: int, db: Session = Depends(get_db), admin: str = Depends(verify_admin)
):
    try:
        _begin_write_transaction(db)
        _settle_due_pass_uses(db)
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
        for booking in yoga_class.bookings:
            if booking.pass_use_consumed and booking.pass_record:
                booking.pass_record.remaining_uses = (booking.pass_record.remaining_uses or 0) + 1
                booking.pass_use_consumed = False
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
