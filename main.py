from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timedelta
from database import engine, SessionLocal, Base
from fastapi.middleware.cors import CORSMiddleware
import models
import uuid
import secrets

# Táblák létrehozása, ha még nem léteznek
Base.metadata.create_all(bind=engine)

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

# Itt állíthatod be a keresztanyád belépési adatait
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
    max_capacity: int = 15 # Itt is 15-re frissítve

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
        max_capacity=yoga_class.max_capacity
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
        # CSAK AZ AKTÍV foglalásokat számoljuk össze a kapacitáshoz
        booked_count = db.query(models.Booking).filter(
            models.Booking.class_id == c.id,
            models.Booking.status == "active"
        ).count()
        free_spots = max(0, c.max_capacity - booked_count)
        
        result.append({
            "id": c.id,
            "title": c.title,
            "start_time": c.start_time,
            "free_spots": free_spots
        })
    return result

@app.post("/bookings/")
def create_booking(booking: BookingRequest, db: Session = Depends(get_db)):
    yoga_class = db.query(models.YogaClass).filter(models.YogaClass.id == booking.class_id).first()
    if not yoga_class:
        raise HTTPException(status_code=404, detail="A jógaóra nem található.")
    
    # 1. SZABÁLY: 45 perccel kezdés előtt lezárul a jelentkezés
    now = datetime.utcnow()
    time_until_class = yoga_class.start_time - now
    if time_until_class < timedelta(minutes=45):
        raise HTTPException(status_code=400, detail="Erre az órára a jelentkezés már lezárult (45 perccel kezdés előtt).")

    # Megkeressük vagy létrehozzuk a usert
    user = db.query(models.User).filter(models.User.email == booking.email).first()
    if not user:
        user = models.User(name=booking.name, email=booking.email)
        db.add(user)
        db.commit()
        db.refresh(user)

    # 2. SZABÁLY: Dupla foglalás megakadályozása (ne foglalhasson be 2 helyet ugyanarra az órára)
    existing_booking = db.query(models.Booking).filter(
        models.Booking.class_id == booking.class_id,
        models.Booking.user_id == user.id,
        models.Booking.status.in_(["active", "waitlisted"])
    ).first()
    if existing_booking:
        raise HTTPException(status_code=400, detail="Már jelentkeztél erre az órára (vagy rajta vagy a várólistán).")

    # 3. SZABÁLY: Kapacitás és várólista logika
    current_active = db.query(models.Booking).filter(
        models.Booking.class_id == booking.class_id,
        models.Booking.status == "active"
    ).count()

    status = "active"
    if current_active >= yoga_class.max_capacity:
        status = "waitlisted"

    new_booking = models.Booking(
        user_id=user.id, 
        class_id=booking.class_id,
        status=status
    )
    db.add(new_booking)
    db.commit()

    if status == "waitlisted":
        return {"message": "A létszám betelt, felkerültél a várólistára!", "status": status}
    
    return {"message": "Sikeres foglalás!", "status": status}

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