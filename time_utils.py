from datetime import datetime, timezone
from zoneinfo import ZoneInfo


APP_TIMEZONE = ZoneInfo("Europe/Budapest")
UTC = timezone.utc


def utc_now_naive() -> datetime:
    """UTC időpont tároláshoz és összehasonlításhoz."""
    return datetime.now(UTC).replace(tzinfo=None)


def to_utc_naive(value: datetime) -> datetime:
    """A kliens naiv idejét magyar helyi időnek tekinti, majd UTC-re normalizálja."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=APP_TIMEZONE)
    return value.astimezone(UTC).replace(tzinfo=None)


def utc_to_local(value: datetime) -> datetime:
    """UTC-ben tárolt, naiv datetime visszaalakítása magyar helyi időre."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(APP_TIMEZONE)
