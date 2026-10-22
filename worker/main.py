"""APScheduler entrypoint. Full jobs wired in M7; M1 keeps process alive."""
from __future__ import annotations

import time

from common.logging import get_logger

log = get_logger("worker.main")


def main() -> None:
    log.info("worker starting (scheduler attached in M7)")
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
