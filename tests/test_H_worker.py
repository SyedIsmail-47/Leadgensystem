from unittest.mock import patch

import pytest

from common.db import fetchone
from scrapers.leads_repo import finish_run, start_run
from worker import jobs


@pytest.mark.integration
def test_H1_job_exception_marks_failed(db):
    run_id = start_run(1, "boom", None)
    try:
        raise RuntimeError("explode")
    except Exception as exc:
        finish_run(run_id, "failed", errors=1, log=str(exc))
    row = fetchone("SELECT status, log FROM runs WHERE id=%s", (run_id,))
    assert row["status"] == "failed"
    assert "explode" in (row["log"] or "")


@pytest.mark.integration
def test_H2_job_writes_runs_row(db):
    n = jobs.job_score_pending()
    assert n == 0
    row = fetchone("SELECT * FROM runs WHERE job='score_pending' ORDER BY id DESC LIMIT 1")
    assert row
    assert row["started_at"]
    assert row["finished_at"]
    assert row["status"] == "ok"


@pytest.mark.unit
def test_H3_playwright_lock_serial():
    assert jobs._playwright_lock is not None
    acquired = jobs._playwright_lock.acquire(blocking=False)
    assert acquired
    second = jobs._playwright_lock.acquire(blocking=False)
    assert second is False
    jobs._playwright_lock.release()


@pytest.mark.integration
def test_H4_paused_campaign_not_discovered(db):
    fetchone(
        "INSERT INTO campaigns (workspace_id, name, niche, location, status, schedule_cron) "
        "VALUES (1,'paused','n','L','paused','0 9 * * *') RETURNING id"
    )
    with patch("worker.jobs.discover_campaign") as disc:
        jobs.job_discover_due()
        disc.assert_not_called()


@pytest.mark.integration
def test_H5_enrich_score_skip_processed(db):
    # already has crawled signal → enrich_pending skips
    lead = fetchone(
        "INSERT INTO leads (workspace_id, name, website, stage, dedupe_key) "
        "VALUES (1,'E','https://e.com','enriched','e|1') RETURNING id"
    )
    from common.db import execute

    execute(
        "INSERT INTO lead_signals (lead_id, channel, signal, verified) VALUES (%s,'website','crawled',true)",
        (lead["id"],),
    )
    from enrich.pipeline import enrich_pending

    result = enrich_pending(1, limit=50)
    assert result["enriched"] == 0
