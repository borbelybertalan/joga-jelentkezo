from datetime import datetime, timedelta

from database import SessionLocal
from migrations import run_migrations
import models
from time_utils import APP_TIMEZONE, to_utc_naive


# 0 = Hétfő, 1 = Kedd, 2 = Szerda, 3 = Csütörtök, 4 = Péntek
WEEKLY_TEMPLATE = [
    {"day": 0, "time": "06:20", "title": "Légzés", "instructor": "", "zoom_available": False, "note": ""},
    {"day": 0, "time": "08:15", "title": "Iyengar", "instructor": "Klára", "zoom_available": True, "note": ""},
    {"day": 0, "time": "17:00", "title": "Iyengar +kötélfal", "instructor": "Klára", "zoom_available": True, "note": "Szükséges otthoni kötélfal!"},
    {"day": 0, "time": "18:45", "title": "Légzés + Aktív mozgás", "instructor": "Mio", "zoom_available": True, "note": ""},
    {"day": 1, "time": "06:20", "title": "Légzés", "instructor": "", "zoom_available": False, "note": ""},
    {"day": 1, "time": "10:00", "title": "Székes ízületlazító", "instructor": "Klára", "zoom_available": True, "note": ""},
    {"day": 1, "time": "15:15", "title": "Iyengar jóga - diák", "instructor": "Klára", "zoom_available": False, "note": "*"},
    {"day": 1, "time": "17:00", "title": "Iyengar jóga", "instructor": "Klára", "zoom_available": True, "note": ""},
    {"day": 2, "time": "06:20", "title": "Légzés", "instructor": "", "zoom_available": False, "note": ""},
    {"day": 2, "time": "08:45", "title": "Iyengar, resztoratív", "instructor": "Klára", "zoom_available": True, "note": ""},
    {"day": 2, "time": "17:00", "title": "Dinamikus Iyengar, I. syllabus ászanái", "instructor": "Mio", "zoom_available": True, "note": ""},
    {"day": 3, "time": "06:20", "title": "Légzés", "instructor": "", "zoom_available": False, "note": ""},
    {"day": 3, "time": "10:00", "title": "Gerincterápia", "instructor": "Klára", "zoom_available": True, "note": "Szükséges otthoni kötélfal!"},
    {"day": 3, "time": "17:00", "title": "Dinamikus Iyengar, jóga és erőnlét", "instructor": "Klára", "zoom_available": True, "note": ""},
    {"day": 4, "time": "06:20", "title": "Légzés", "instructor": "", "zoom_available": False, "note": ""},
    {"day": 4, "time": "08:15", "title": "Iyengar aktív", "instructor": "Klára", "zoom_available": True, "note": ""},
    {"day": 4, "time": "15:00", "title": "Jin jóga", "instructor": "Timi", "zoom_available": False, "note": ""},
]


def generate_next_year(days_ahead: int = 365) -> int:
    """Idempotensen feltölti a következő időszak óráit; a dátumok UTC-ben kerülnek az adatbázisba."""
    run_migrations()
    db = SessionLocal()
    now_local = datetime.now(APP_TIMEZONE).replace(tzinfo=None)
    end_date = now_local + timedelta(days=days_ahead)
    current_week_monday = (now_local - timedelta(days=now_local.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    classes_added = 0

    try:
        while current_week_monday < end_date:
            for session in WEEKLY_TEMPLATE:
                target_date = current_week_monday + timedelta(days=session["day"])
                if target_date >= end_date:
                    continue

                hour, minute = map(int, session["time"].split(":"))
                local_start_time = target_date.replace(hour=hour, minute=minute)
                if local_start_time < now_local:
                    continue

                start_time = to_utc_naive(local_start_time)
                existing_class = (
                    db.query(models.YogaClass)
                    .filter(
                        models.YogaClass.start_time == start_time,
                        models.YogaClass.title == session["title"],
                    )
                    .first()
                )
                if not existing_class:
                    db.add(
                        models.YogaClass(
                            title=session["title"],
                            start_time=start_time,
                            max_capacity=15,
                            instructor=session["instructor"] or None,
                            zoom_available=session["zoom_available"],
                            note=session["note"] or None,
                        )
                    )
                    classes_added += 1
            current_week_monday += timedelta(days=7)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return classes_added


if __name__ == "__main__":
    print(f"Generálás kész! {generate_next_year()} db új óra került az adatbázisba.")
