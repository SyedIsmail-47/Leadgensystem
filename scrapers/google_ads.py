"""Google Ads Transparency checker (STRETCH — soft-fail)."""
from __future__ import annotations

from common.db import execute
from common.logging import get_logger

log = get_logger("scrapers.google_ads")


def check_google_ads(lead_id: int, name: str, website: str | None = None) -> bool:
    try:
        log.info("google_ads check skipped/stub for lead=%s name=%s", lead_id, name)
        execute(
            """
            INSERT INTO lead_signals (lead_id, channel, signal, value, verified)
            VALUES (%s, 'ads', 'google_ads_checked', %s, false)
            """,
            (lead_id, name[:200]),
        )
        return False
    except Exception:
        log.exception("google_ads failed lead=%s", lead_id)
        return False
