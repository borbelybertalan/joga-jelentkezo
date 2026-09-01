import base64
import binascii
import hashlib
import hmac
import json
import os
import time
from datetime import timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# A modul importja betölti a projekt gyökerében lévő .env fájlt, mielőtt a titkokat olvassuk.
import config


def _required_secret(name: str, minimum_length: int = 1) -> str:
    value = os.getenv(name, "")
    if len(value) < minimum_length:
        raise RuntimeError(
            f"A(z) {name} környezeti változó hiányzik vagy túl rövid. "
            "Másold a .env.example fájlt .env néven, és adj meg biztonságos értékeket."
        )
    return value


ADMIN_USERNAME = _required_secret("ADMIN_USERNAME")
ADMIN_PASSWORD = _required_secret("ADMIN_PASSWORD", minimum_length=12)
APP_SECRET = _required_secret("APP_SECRET", minimum_length=32).encode("utf-8")
TOKEN_TTL = timedelta(hours=8)
bearer_scheme = HTTPBearer(auto_error=False)


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_admin_token(username: str) -> tuple[str, int]:
    expires_at = int(time.time() + TOKEN_TTL.total_seconds())
    payload = _encode(json.dumps({"sub": username, "exp": expires_at}).encode("utf-8"))
    signature = _encode(hmac.new(APP_SECRET, payload.encode("ascii"), hashlib.sha256).digest())
    return f"{payload}.{signature}", expires_at


def verify_password(username: str, password: str) -> bool:
    return hmac.compare_digest(username, ADMIN_USERNAME) and hmac.compare_digest(
        password, ADMIN_PASSWORD
    )


def verify_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Érvénytelen vagy lejárt admin munkamenet.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized

    try:
        payload, signature = credentials.credentials.split(".", 1)
        expected_signature = _encode(
            hmac.new(APP_SECRET, payload.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(signature, expected_signature):
            raise ValueError("invalid signature")
        data = json.loads(_decode(payload))
        if data.get("sub") != ADMIN_USERNAME or int(data["exp"]) <= time.time():
            raise ValueError("expired token")
    except (ValueError, KeyError, TypeError, UnicodeDecodeError, binascii.Error, json.JSONDecodeError):
        raise unauthorized

    return ADMIN_USERNAME
