from datetime import datetime, timedelta

import models
from database import SessionLocal
from migrations import run_migrations
from time_utils import APP_TIMEZONE, to_utc_naive, utc_to_local

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


def sync_existing_class_metadata(db) -> int:
    """A már létrehozott, sablon szerinti órák kiegészítő adatait helyreállítja."""
    sessions_by_slot = {
        (session["day"], session["time"], session["title"]): session
        for session in WEEKLY_TEMPLATE
    }
    updated_count = 0

    for yoga_class in db.query(models.YogaClass).all():
        local_start_time = utc_to_local(yoga_class.start_time)
        session = sessions_by_slot.get(
            (
                local_start_time.weekday(),
                local_start_time.strftime("%H:%M"),
                yoga_class.title,
            )
        )
        if not session:
            continue

        expected_values = {
            "instructor": session["instructor"] or None,
            "zoom_available": session["zoom_available"],
            "note": session["note"] or None,
        }
        if any(getattr(yoga_class, field) != value for field, value in expected_values.items()):
            for field, value in expected_values.items():
                setattr(yoga_class, field, value)
            updated_count += 1

    return updated_count


def sync_existing_schedule() -> int:
    """A helyi adatbázisban korrigálja a heti sablonhoz tartozó óraadatokat."""
    run_migrations()
    db = SessionLocal()
    try:
        updated_count = sync_existing_class_metadata(db)
        db.commit()
        return updated_count
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


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
