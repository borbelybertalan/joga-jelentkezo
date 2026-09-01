import secrets
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from time_utils import utc_now_naive


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True, index=True)
    role: Mapped[str] = mapped_column(String(30), nullable=False, default="student")

    bookings: Mapped[list["Booking"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class YogaClass(Base):
    __tablename__ = "yoga_classes"
    __table_args__ = (CheckConstraint("max_capacity >= 1", name="ck_yoga_classes_capacity"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    # Az adatbázisban minden időpont UTC, timezone nélküli datetime-ként szerepel.
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    max_capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    instructor: Mapped[str | None] = mapped_column(String(120), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    zoom_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    bookings: Mapped[list["Booking"]] = relationship(
        back_populates="yoga_class", cascade="all, delete-orphan", passive_deletes=True
    )


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        UniqueConstraint("user_id", "class_id", name="uq_bookings_user_class"),
        CheckConstraint(
            "status IN ('active', 'waitlisted', 'cancelled')", name="ck_bookings_status"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    class_id: Mapped[int] = mapped_column(
        ForeignKey("yoga_classes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    booking_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now_naive)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    cancel_token: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, default=lambda: secrets.token_urlsafe(32)
    )

    user: Mapped[User] = relationship(back_populates="bookings")
    yoga_class: Mapped[YogaClass] = relationship(back_populates="bookings")
