"""Lead dedupe key helpers."""
from __future__ import annotations

import re
from urllib.parse import urlparse


def _norm(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _domain(website: str | None) -> str:
    if not website:
        return ""
    raw = website.strip()
    if not raw.startswith("http"):
        raw = "https://" + raw
    try:
        host = urlparse(raw).netloc.lower()
    except Exception:
        return _norm(website)
    if host.startswith("www."):
        host = host[4:]
    return host


def _phone_digits(phone: str | None) -> str:
    if not phone:
        return ""
    digits = re.sub(r"\D+", "", phone)
    # Normalize PK local 03xxxxxxxxx ↔ 923xxxxxxxxx
    if digits.startswith("0") and len(digits) == 11:
        digits = "92" + digits[1:]
    if digits.startswith("920") and len(digits) >= 12:
        digits = "92" + digits[3:]
    return digits


def dedupe_key(name: str, phone: str | None = None, website: str | None = None) -> str:
    """normalized(name) + phone digits or domain."""
    base = _norm(name)
    phone_part = _phone_digits(phone)
    domain = _domain(website)
    suffix = phone_part or domain or "na"
    return f"{base}|{suffix}"
