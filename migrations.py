from sqlalchemy import inspect, text

from database import Base, SessionLocal, engine
import models
from time_utils import to_utc_naive


MIGRATION_TABLE = "schema_migrations"
LEGACY_METADATA_MIGRATION = "20260901_add_yoga_class_metadata"
UTC_TIMES_MIGRATION = "20260901_store_class_times_as_utc"
BOOKING_INDEX_MIGRATION = "20260901_unique_booking_per_user_and_class"
BOOKING_CONSTRAINTS_MIGRATION = "20260901_rebuild_bookings_with_constraints"


def _record_migration(connection, migration_id: str) -> None:
    connection.execute(
        text(f"INSERT INTO {MIGRATION_TABLE} (id) VALUES (:id)"), {"id": migration_id}
    )


def _is_applied(connection, migration_id: str) -> bool:
    return connection.execute(
        text(f"SELECT 1 FROM {MIGRATION_TABLE} WHERE id = :id"), {"id": migration_id}
    ).first() is not None


def run_migrations() -> None:
    """Idempotens, verziózott sémamigrációk; nem írnak felül üzleti adatot."""
    Base.metadata.create_all(bind=engine)

    with engine.begin() as connection:
        connection.execute(
            text(
                f"CREATE TABLE IF NOT EXISTS {MIGRATION_TABLE} ("
                "id VARCHAR(100) PRIMARY KEY, applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
        )

        if not _is_applied(connection, LEGACY_METADATA_MIGRATION):
            columns = {column["name"] for column in inspect(connection).get_columns("yoga_classes")}
            if "instructor" not in columns:
                connection.execute(text("ALTER TABLE yoga_classes ADD COLUMN instructor VARCHAR(120)"))
            if "note" not in columns:
                connection.execute(text("ALTER TABLE yoga_classes ADD COLUMN note VARCHAR(500)"))
            if "zoom_available" not in columns:
                connection.execute(
                    text(
                        "ALTER TABLE yoga_classes "
                        "ADD COLUMN zoom_available BOOLEAN NOT NULL DEFAULT 0"
                    )
                )
            _record_migration(connection, LEGACY_METADATA_MIGRATION)

        if not _is_applied(connection, BOOKING_INDEX_MIGRATION):
            duplicates = connection.execute(
                text(
                    "SELECT user_id, class_id FROM bookings "
                    "GROUP BY user_id, class_id HAVING COUNT(*) > 1 LIMIT 1"
                )
            ).first()
            if duplicates:
                raise RuntimeError(
                    "A foglalási egyedi index nem hozható létre: duplikált foglalások vannak. "
                    "Előbb ezeket rendezd."
                )
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_bookings_user_class "
                    "ON bookings (user_id, class_id)"
                )
            )
            _record_migration(connection, BOOKING_INDEX_MIGRATION)

        if not _is_applied(connection, BOOKING_CONSTRAINTS_MIGRATION):
            invalid_rows = connection.execute(
                text(
                    "SELECT COUNT(*) FROM bookings WHERE user_id IS NULL OR class_id IS NULL "
                    "OR booking_time IS NULL OR cancel_token IS NULL "
                    "OR status NOT IN ('active', 'waitlisted', 'cancelled')"
                )
            ).scalar_one()
            if invalid_rows:
                raise RuntimeError(
                    "A foglalási tábla nem építhető újra: hiányos vagy érvénytelen foglalási rekordok vannak."
                )

            connection.execute(
                text(
                    "CREATE TABLE bookings_new ("
                    "id INTEGER NOT NULL PRIMARY KEY, "
                    "user_id INTEGER NOT NULL, "
                    "class_id INTEGER NOT NULL, "
                    "booking_time DATETIME NOT NULL, "
                    "status VARCHAR(20) NOT NULL CHECK (status IN ('active', 'waitlisted', 'cancelled')), "
                    "cancel_token VARCHAR(128) NOT NULL UNIQUE, "
                    "CONSTRAINT uq_bookings_user_class UNIQUE (user_id, class_id), "
                    "FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, "
                    "FOREIGN KEY(class_id) REFERENCES yoga_classes (id) ON DELETE CASCADE)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO bookings_new (id, user_id, class_id, booking_time, status, cancel_token) "
                    "SELECT id, user_id, class_id, booking_time, status, cancel_token FROM bookings"
                )
            )
            connection.execute(text("DROP TABLE bookings"))
            connection.execute(text("ALTER TABLE bookings_new RENAME TO bookings"))
            connection.execute(text("CREATE INDEX ix_bookings_user_id ON bookings (user_id)"))
            connection.execute(text("CREATE INDEX ix_bookings_class_id ON bookings (class_id)"))
            connection.execute(text("CREATE INDEX ix_bookings_status ON bookings (status)"))
            _record_migration(connection, BOOKING_CONSTRAINTS_MIGRATION)

    # A korábbi felület lokális magyar időt tárolt timezone nélkül. Ezt egyszer alakítjuk UTC-re.
    with engine.begin() as connection:
        if _is_applied(connection, UTC_TIMES_MIGRATION):
            return

        session = SessionLocal(bind=connection)
        try:
            for yoga_class in session.query(models.YogaClass).yield_per(200):
                if yoga_class.start_time is not None:
                    yoga_class.start_time = to_utc_naive(yoga_class.start_time)
            session.flush()
            _record_migration(connection, UTC_TIMES_MIGRATION)
        finally:
            session.close()
