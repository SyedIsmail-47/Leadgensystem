"""Email and phone validators."""
from __future__ import annotations

import dns.resolver
import phonenumbers
from email_validator import EmailNotValidError, validate_email as _validate_email

from common.config import get_settings
from common.logging import get_logger

log = get_logger("enrich.validators")


def validate_email(address: str | None) -> tuple[str | None, bool]:
    """Return (normalized_email, mx_ok)."""
    if not address:
        return None, False
    try:
        info = _validate_email(address, check_deliverability=False)
        email = info.normalized
    except EmailNotValidError:
        return None, False

    domain = email.rsplit("@", 1)[-1]
    mx_ok = False
    try:
        answers = dns.resolver.resolve(domain, "MX")
        mx_ok = len(list(answers)) > 0
    except Exception:
        try:
            answers = dns.resolver.resolve(domain, "A")
            mx_ok = len(list(answers)) > 0
        except Exception:
            mx_ok = False
    return email, mx_ok


def normalize_phone(phone: str | None, region: str | None = None) -> tuple[str | None, bool]:
    """Return (E.164 phone, valid)."""
    if not phone:
        return None, False
    region = region or get_settings().default_region
    try:
        parsed = phonenumbers.parse(phone, region)
        valid = phonenumbers.is_valid_number(parsed)
        if not valid:
            return None, False
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164), True
    except Exception:
        return None, False
