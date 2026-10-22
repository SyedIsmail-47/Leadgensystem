"""APScheduler worker entrypoint."""
from __future__ import annotations

import signal
import sys
import time

from apscheduler.schedulers.background import BackgroundScheduler

from common.logging import get_logger
from worker import jobs

log = get_logger("worker.main")


def main() -> None:
    log.info("worker starting")
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(jobs.job_discover_due, "cron", minute=0, id="discover_due", replace_existing=True)
    scheduler.add_job(jobs.job_enrich_pending, "interval", minutes=15, id="enrich", replace_existing=True)
    scheduler.add_job(jobs.job_score_pending, "interval", minutes=20, id="score", replace_existing=True)
    scheduler.add_job(jobs.job_send_due, "interval", minutes=10, id="send", replace_existing=True)
    scheduler.add_job(jobs.job_ads_stretch, "cron", hour=3, minute=30, id="ads", replace_existing=True)
    scheduler.start()
    log.info("scheduler started")

    def _stop(*_args: object) -> None:
        log.info("shutting down")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
