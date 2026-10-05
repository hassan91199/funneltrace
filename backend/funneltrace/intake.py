import re
from dataclasses import dataclass

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MIN_PHONE_DIGITS = 7


@dataclass(frozen=True)
class InboundLead:
    """One inbound contact, normalized the same way whatever channel it came from."""

    channel: str
    name: str
    email: str | None
    phone: str | None
    normalized_email: str | None
    normalized_phone: str | None
    message: str
    raw_payload: dict


def normalize_email(raw: str | None) -> str | None:
    """Trim and lowercase. Empty becomes None; a non-empty malformed address raises."""
    value = (raw or "").strip().lower()
    if not value:
        return None
    if not _EMAIL_RE.match(value):
        raise ValueError(f"invalid email: {raw!r}")
    return value


def normalize_phone(raw: str | None) -> str | None:
    """Digits only, international form without '+' (a leading 00 is dropped).

    Numbers too short to be usable become None. Numbers without a country code
    can't be resolved here, so they are kept as the digits given.
    """
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("00"):
        digits = digits[2:]
    return digits if len(digits) >= _MIN_PHONE_DIGITS else None


def _required(payload: dict, key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def normalize_web_form(payload: dict) -> InboundLead:
    name = _required(payload, "name")
    message = _required(payload, "message")
    email = normalize_email(payload.get("email"))
    phone = normalize_phone(payload.get("phone"))
    if email is None and phone is None:
        raise ValueError("an email or phone is required to reach the lead")
    return InboundLead(
        channel="web_form",
        name=name,
        email=(payload.get("email") or "").strip() or None,
        phone=(payload.get("phone") or "").strip() or None,
        normalized_email=email,
        normalized_phone=phone,
        message=message,
        raw_payload=dict(payload),
    )


def normalize_whatsapp(payload: dict) -> InboundLead:
    number = normalize_phone(payload.get("from"))
    if number is None:
        raise ValueError("from must be a usable phone number")
    message = _required(payload, "text")
    return InboundLead(
        channel="whatsapp",
        name=str(payload.get("profile_name") or "").strip() or f"+{number}",
        email=None,
        phone=str(payload["from"]).strip(),
        normalized_email=None,
        normalized_phone=number,
        message=message,
        raw_payload=dict(payload),
    )
