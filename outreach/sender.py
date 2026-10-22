"""SMTP sender with approval and suppression gates."""
from __future__ import annotations

import random
import smtplib
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any

from common.db import execute, fetchone
from common.logging import get_logger
from outreach.unsubscribe import is_suppressed

log = get_logger("outreach.sender")


def can_send(sender: dict[str, Any] | None) -> bool:
    if not sender:
        return False
    if not (sender.get("physical_address") or "").strip():
        return False
    if not sender.get("smtp_verified_at"):
        return False
    if not sender.get("smtp_host") or not sender.get("from_email"):
        return False
    return True


def _within_window(sender: dict[str, Any]) -> bool:
    start = int(sender.get("send_window_start") or 0)
    end = int(sender.get("send_window_end") or 23)
    hour = datetime.now(timezone.utc).hour
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end


def _sent_today(workspace_id: int, sender_id: int) -> int:
    row = fetchone(
        """
        SELECT COUNT(*) AS c FROM outreach_steps os
        JOIN leads l ON l.id = os.lead_id
        JOIN campaigns c ON c.id = l.campaign_id
        WHERE os.workspace_id = %s
          AND c.sender_profile_id = %s
          AND os.status = 'sent'
          AND os.sent_at::date = CURRENT_DATE
        """,
        (workspace_id, sender_id),
    )
    return int(row["c"] or 0) if row else 0


def send_email(
    sender: dict[str, Any],
    to_email: str,
    subject: str,
    body: str,
) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{sender['sender_name']} <{sender['from_email']}>"
    msg["To"] = to_email
    if sender.get("reply_to"):
        msg["Reply-To"] = sender["reply_to"]
    msg.set_content(body)
    port = int(sender.get("smtp_port") or 587)
    host = sender.get("smtp_host") or "localhost"
    with smtplib.SMTP(host, port, timeout=30) as server:
        server.ehlo()
        # Plain SMTP (e.g. local dummy :1025) has no STARTTLS — skip when unsupported.
        if server.has_extn("starttls") and port not in (25, 1025):
            server.starttls()
            server.ehlo()
        if sender.get("smtp_user"):
            server.login(sender["smtp_user"], sender.get("smtp_pass_enc") or "")
        server.send_message(msg)


def send_step(step_id: int) -> bool:
    step = fetchone("SELECT * FROM outreach_steps WHERE id = %s", (step_id,))
    if not step or step["status"] not in ("approved", "pending"):
        return False
    if step["status"] != "approved":
        log.info("skip step %s not approved", step_id)
        return False
    if step.get("scheduled_for") and step["scheduled_for"] > datetime.now(timezone.utc):
        log.info("skip step %s not scheduled yet", step_id)
        return False

    lead = fetchone("SELECT * FROM leads WHERE id = %s", (step["lead_id"],))
    if not lead or not lead.get("email"):
        execute(
            "UPDATE outreach_steps SET status='skipped', error=%s WHERE id=%s",
            ("no email", step_id),
        )
        return False
    if lead.get("stage") == "replied":
        execute(
            "UPDATE outreach_steps SET status='skipped', error=%s WHERE id=%s",
            ("lead replied", step_id),
        )
        return False

    if is_suppressed(int(step["workspace_id"]), lead["email"]):
        execute(
            "UPDATE outreach_steps SET status='skipped', error=%s WHERE id=%s",
            ("suppressed", step_id),
        )
        return False

    camp = None
    sender = None
    if lead.get("campaign_id"):
        camp = fetchone("SELECT * FROM campaigns WHERE id = %s", (lead["campaign_id"],))
        if camp and camp.get("sender_profile_id"):
            sender = fetchone(
                "SELECT * FROM sender_profiles WHERE id = %s",
                (camp["sender_profile_id"],),
            )

    if not can_send(sender):
        execute(
            "UPDATE outreach_steps SET status='failed', error=%s WHERE id=%s",
            ("sender not ready (address + SMTP test required)", step_id),
        )
        return False

    assert sender is not None
    if not _within_window(sender):
        log.info("outside send window for step %s", step_id)
        return False

    daily_limit = int(sender.get("daily_limit") or 20)
    if _sent_today(int(step["workspace_id"]), int(sender["id"])) >= daily_limit:
        log.info("daily limit reached")
        return False

    try:
        send_email(sender, lead["email"], step["subject"] or "", step["body"] or "")
        execute(
            """
            UPDATE outreach_steps SET status='sent', sent_at=now(), error=NULL WHERE id=%s
            """,
            (step_id,),
        )
        execute(
            """
            UPDATE leads SET stage='contacted', updated_at=now()
            WHERE id=%s AND stage IN ('approved','scored','enriched','new')
            """,
            (lead["id"],),
        )
        # Rate limit; skip long delay for local dummy SMTP self-tests.
        if (sender.get("smtp_host") or "") not in ("127.0.0.1", "localhost"):
            time.sleep(random.uniform(60, 120))
        return True
    except Exception as exc:
        log.exception("send failed")
        execute(
            "UPDATE outreach_steps SET status='failed', error=%s WHERE id=%s",
            (str(exc)[:500], step_id),
        )
        return False


def send_due_steps(limit: int = 20) -> int:
    from common.db import fetchall

    rows = fetchall(
        """
        SELECT id FROM outreach_steps
        WHERE status = 'approved'
          AND (scheduled_for IS NULL OR scheduled_for <= now())
        ORDER BY scheduled_for NULLS FIRST, id
        LIMIT %s
        """,
        (limit,),
    )
    sent = 0
    for row in rows:
        if send_step(int(row["id"])):
            sent += 1
    return sent
