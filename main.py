from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
from database import engine, SessionLocal, Base
from fastapi.middleware.cors import CORSMiddleware
import models

# Táblák létrehozása, ha még nem léteznek
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Jóga Foglalási Rendszer")

# CORS engedélyezése (fejlesztés alatt mindenhonnan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- PYDANTIC SÉMÁK (Bemeneti adatok validálása) ---
class UserCreate(BaseModel):
    name: str
    email: str

class ClassCreate(BaseModel):
    title: str
    start_time: datetime
    max_capacity: int = 10

class BookingRequest(BaseModel):
    name: str
    email: str
    class_id: int

# --- API VÉGPONTOK ---
@app.get("/")
def read_root():
    return {"message": "A jóga foglalási rendszer backendje sikeresen elindult!"}

@app.post("/users/")
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Ez az e-mail cím már regisztrálva van.")
    new_user = models.User(name=user.name, email=user.email)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.post("/classes/")
def create_class(yoga_class: ClassCreate, db: Session = Depends(get_db)):
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
        booked_count = db.query(models.Booking).filter(models.Booking.class_id == c.id).count()
        free_spots = c.max_capacity - booked_count
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
    
    current_bookings = db.query(models.Booking).filter(models.Booking.class_id == booking.class_id).count()
    if current_bookings >= yoga_class.max_capacity:
        raise HTTPException(status_code=400, detail="Sajnáljuk, erre az órára már nincs több hely.")

    user = db.query(models.User).filter(models.User.email == booking.email).first()
    if not user:
        user = models.User(name=booking.name, email=booking.email)
        db.add(user)
        db.commit()
        db.refresh(user)

    new_booking = models.Booking(user_id=user.id, class_id=booking.class_id)
    db.add(new_booking)
    db.commit()
    return {"message": "Sikeres foglalás!"}

# ÚJ VÉGPONT: Keresztanyádnak a jelentkezők listázásához
@app.get("/classes/{class_id}/bookings/")
def get_class_bookings(class_id: int, db: Session = Depends(get_db)):
    bookings = db.query(models.Booking).filter(models.Booking.class_id == class_id).all()
    result = []
    for b in bookings:
        user = db.query(models.User).filter(models.User.id == b.user_id).first()
        if user:
            result.append({"name": user.name, "email": user.email})
    return result