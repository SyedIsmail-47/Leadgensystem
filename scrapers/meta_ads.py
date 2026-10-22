"""Meta Ad Library checker (STRETCH — soft-fail)."""
from __future__ import annotations

from common.db import execute
from common.logging import get_logger

log = get_logger("scrapers.meta_ads")


def check_meta_ads(lead_id: int, name: str, website: str | None = None) -> bool:
    """Return True if running ads detected. Never raises to caller path if used carefully."""
    try:
        # Soft stub: do not block pipeline. Full Playwright scrape is stretch.
        log.info("meta_ads check skipped/stub for lead=%s name=%s", lead_id, name)
        execute(
            """
            INSERT INTO lead_signals (lead_id, channel, signal, value, verified)
            VALUES (%s, 'ads', 'meta_ads_checked', %s, false)
            """,
            (lead_id, name[:200]),
        )
        return False
    except Exception:
        log.exception("meta_ads failed lead=%s", lead_id)
        return False
