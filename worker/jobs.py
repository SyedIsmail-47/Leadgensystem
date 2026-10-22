"""Scheduled job implementations. One Playwright job at a time."""
from __future__ import annotations

import threading
from typing import Any

from common.db import fetchall, fetchone
from common.logging import get_logger
from enrich.pipeline import enrich_pending
from outreach.sender import send_due_steps
from scrapers.campaign_discover import discover_campaign
from scrapers.leads_repo import finish_run, start_run
from scoring.engine import score_pending

log = get_logger("worker.jobs")
_playwright_lock = threading.Lock()


def job_discover_due() -> None:
    """Run discovery for active campaigns with a schedule (or all active once daily via cron)."""
    camps = fetchall(
        """
        SELECT id, schedule_cron, status FROM campaigns
        WHERE status = 'active' AND schedule_cron IS NOT NULL AND schedule_cron <> ''
        """
    )
    for c in camps:
        try:
            with _playwright_lock:
                discover_campaign(int(c["id"]))
        except Exception:
            log.exception("discover failed campaign=%s", c["id"])


def job_discover_campaign(campaign_id: int) -> int:
    with _playwright_lock:
        return discover_campaign(campaign_id)


def job_enrich_pending() -> dict[str, int]:
    return enrich_pending(limit=50)


def job_score_pending() -> int:
    return score_pending(limit=200)


def job_send_due() -> int:
    run_id = start_run(1, "send_due_steps", None)
    try:
        n = send_due_steps(limit=20)
        finish_run(run_id, "ok", found=n)
        return n
    except Exception as exc:
        finish_run(run_id, "failed", errors=1, log=str(exc))
        raise


def job_ads_stretch() -> None:
    """Soft-fail stretch: try ads scrapers for scored leads lacking ads signals."""
    from scrapers.google_ads import check_google_ads
    from scrapers.meta_ads import check_meta_ads

    leads = fetchall(
        """
        SELECT l.id, l.name, l.website FROM leads l
        WHERE l.stage IN ('enriched','scored','approved')
          AND NOT EXISTS (
            SELECT 1 FROM lead_signals s WHERE s.lead_id = l.id AND s.signal = 'running_ads'
          )
        ORDER BY l.score DESC NULLS LAST LIMIT 10
        """
    )
    for lead in leads:
        try:
            check_meta_ads(int(lead["id"]), lead.get("name") or "", lead.get("website"))
        except Exception:
            log.exception("meta ads soft-fail lead=%s", lead["id"])
        try:
            check_google_ads(int(lead["id"]), lead.get("name") or "", lead.get("website"))
        except Exception:
            log.exception("google ads soft-fail lead=%s", lead["id"])


def reload_campaign_schedules(scheduler: Any) -> None:
    """Placeholder for dynamic cron — jobs poll active campaigns each tick."""
    _ = scheduler
    row = fetchone("SELECT COUNT(*) AS c FROM campaigns WHERE status='active'")
    log.info("active campaigns=%s", row["c"] if row else 0)
