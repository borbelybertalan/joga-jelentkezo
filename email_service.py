import os
import smtplib
from email.message import EmailMessage
from typing import Any


def _smtp_settings() -> dict[str, str] | None:
    host = os.getenv("SMTP_HOST", "").strip()
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM", "").strip()
    if not all((host, username, password, sender)):
        return None
    return {"host": host, "username": username, "password": password, "sender": sender}


def send_booking_confirmation(
    *,
    recipient: str,
    class_title: str,
    class_start: str,
    booking_status: str,
    cancel_url: str,
    pass_summary: dict[str, Any] | None,
    payment_notice: str | None,
) -> bool:
    """Küldés Brevo SMTP-vel vagy bármely szabványos SMTP szolgáltatóval.

    Hiányzó SMTP beállítás esetén a foglalás ettől még sikeres marad; a rendszer
    ilyenkor False értékkel jelzi, hogy nincs tényleges e-mail-küldés.
    """
    settings = _smtp_settings()
    if not settings:
        return False

    if pass_summary:
        pass_type = "havi bérlet" if pass_summary["type"] == "monthly" else "8 alkalmas bérlet"
        pass_text = f"Bérleted: {pass_type}. Érvényes eddig: {pass_summary['valid_until']}."
        if pass_summary["remaining_uses"] is not None:
            pass_text += f" Hátralévő alkalmak: {pass_summary['remaining_uses']}."
    else:
        pass_text = payment_notice or "A bérletet vagy az egyszeri jegyet személyesen kell rendezned."

    status_text = "Várólistára kerültél." if booking_status == "waitlisted" else "Sikeres a foglalásod."
    message = EmailMessage()
    message["Subject"] = f"Jógaóra foglalás – {class_title}"
    message["From"] = settings["sender"]
    message["To"] = recipient
    message.set_content(
        "\n".join(
            [
                "Szia!",
                "",
                status_text,
                f"Óra: {class_title}",
                f"Időpont: {class_start}",
                "",
                pass_text,
                "",
                "Lemondás (legkésőbb 12 órával az óra előtt):",
                cancel_url,
            ]
        )
    )

    try:
        port = int(os.getenv("SMTP_PORT", "587"))
        timeout = float(os.getenv("SMTP_TIMEOUT_SECONDS", "10"))
        with smtplib.SMTP(settings["host"], port, timeout=timeout) as server:
            if os.getenv("SMTP_USE_TLS", "true").casefold() not in {"0", "false", "no"}:
                server.starttls()
            server.login(settings["username"], settings["password"])
            server.send_message(message)
        return True
    except (OSError, ValueError, smtplib.SMTPException):
        return False
