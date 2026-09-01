import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def _load_local_env() -> None:
    """Minimális .env betöltés külső függőség nélkül; a valódi környezeti változó elsőbbséget élvez."""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_local_env()


def csv_environment(name: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]
