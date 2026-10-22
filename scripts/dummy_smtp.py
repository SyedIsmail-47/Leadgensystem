"""Catch-all local SMTP for self-tests. Saves messages under /tmp or ./tmp_mail."""
from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from aiosmtpd.controller import Controller

OUT = Path(__file__).resolve().parents[1] / "tmp_mail"
OUT.mkdir(exist_ok=True)


class Handler:
    async def handle_DATA(self, server, session, envelope):  # noqa: N802
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        path = OUT / f"mail_{ts}.eml"
        content = (
            f"From: {envelope.mail_from}\n"
            f"To: {', '.join(envelope.rcpt_tos)}\n\n"
            f"{envelope.content.decode('utf-8', errors='replace')}"
        )
        path.write_text(content, encoding="utf-8")
        print(f"CAUGHT {path.name} to={envelope.rcpt_tos}", flush=True)
        return "250 OK"


if __name__ == "__main__":
    controller = Controller(Handler(), hostname="127.0.0.1", port=1025)
    controller.start()
    print("dummy SMTP listening on 127.0.0.1:1025", flush=True)
    try:
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        controller.stop()
