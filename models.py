from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from database import Base
import datetime
import uuid

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    role = Column(String, default="student") 
    
    # Kapcsolat a foglalasokhoz
    bookings = relationship("Booking", back_populates="user")

class YogaClass(Base):
    __tablename__ = "yoga_classes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    start_time = Column(DateTime)
    max_capacity = Column(Integer, default=15) 
    
    # Kapcsolat a foglalasokhoz
    bookings = relationship("Booking", back_populates="yoga_class")

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    class_id = Column(Integer, ForeignKey("yoga_classes.id"))
    booking_time = Column(DateTime, default=datetime.datetime.utcnow)
    
    # ÚJ OSZLOPOK:
    # Státusz: lehet "active", "waitlisted" vagy "cancelled"
    status = Column(String, default="active") 
    
    # Egyedi azonosító a lemondáshoz, ami az e-mail linkbe kerül
    cancel_token = Column(String, default=lambda: str(uuid.uuid4()), unique=True)
    
    # Visszautalas a szulo tablakra
    user = relationship("User", back_populates="bookings")
    yoga_class = relationship("YogaClass", back_populates="bookings")