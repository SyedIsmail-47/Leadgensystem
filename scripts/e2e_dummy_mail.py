"""End-to-end outreach self-test against local dummy SMTP + dummy recipient."""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from common.db import execute, fetchall, fetchone  # noqa: E402
from outreach.sender import can_send, send_email, send_step  # noqa: E402
from outreach.sequences import approve_steps, enqueue_sequence  # noqa: E402
from outreach.unsubscribe import is_suppressed, make_token, parse_token, suppress  # noqa: E402

DUMMY_TO = "dummy.lead@example.com"
MAIL_DIR = ROOT / "tmp_mail"


def ensure_sender() -> dict:
    existing = fetchone(
        "SELECT * FROM sender_profiles WHERE workspace_id = 1 AND from_email = %s",
        ("demo@leadgensystem.local",),
    )
    if existing:
        execute(
            """
            UPDATE sender_profiles SET
              sender_name=%s, company=%s, physical_address=%s,
              smtp_host=%s, smtp_port=%s, smtp_user=NULL, smtp_pass_enc=NULL,
              daily_limit=%s, send_window_start=%s, send_window_end=%s, timezone=%s,
              smtp_verified_at=%s
            WHERE id=%s
            """,
            (
                "Demo Sender",
                "Leadgensystem Demo Co",
                "123 Demo Street, Lahore, PK",
                "127.0.0.1",
                1025,
                50,
                0,
                23,
                "UTC",
                datetime.now(timezone.utc),
                existing["id"],
            ),
        )
        return fetchone("SELECT * FROM sender_profiles WHERE id=%s", (existing["id"]))  # type: ignore

    row = fetchone(
        """
        INSERT INTO sender_profiles (
          workspace_id, sender_name, company, from_email, reply_to, domain,
          physical_address, smtp_host, smtp_port, daily_limit,
          send_window_start, send_window_end, timezone, smtp_verified_at
        ) VALUES (
          1, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        ) RETURNING *
        """,
        (
            "Demo Sender",
            "Leadgensystem Demo Co",
            "demo@leadgensystem.local",
            "demo@leadgensystem.local",
            "leadgensystem.local",
            "123 Demo Street, Lahore, PK",
            "127.0.0.1",
            1025,
            50,
            0,
            23,
            "UTC",
            datetime.now(timezone.utc),
        ),
    )
    return row  # type: ignore


def ensure_lead(sender_id: int) -> int:
    camp = fetchone("SELECT id FROM campaigns WHERE workspace_id=1 ORDER BY id LIMIT 1")
    if not camp:
        camp = fetchone(
            """
            INSERT INTO campaigns (workspace_id, name, niche, location, status, offer_profile_id, sender_profile_id, scoring_profile_id)
            VALUES (1, 'Dummy Mail Campaign', 'dentist', 'Lahore', 'active', 1, %s, 1)
            RETURNING id
            """,
            (sender_id,),
        )
    else:
        execute(
            "UPDATE campaigns SET sender_profile_id=%s, offer_profile_id=COALESCE(offer_profile_id,1) WHERE id=%s",
            (sender_id, camp["id"]),
        )
    cid = int(camp["id"])

    lead = fetchone(
        "SELECT id FROM leads WHERE workspace_id=1 AND email=%s",
        (DUMMY_TO,),
    )
    if lead:
        lid = int(lead["id"])
        execute(
            "UPDATE leads SET campaign_id=%s, stage='approved', name=%s, city=%s, category=%s WHERE id=%s",
            (cid, "Dummy Dental Clinic", "Lahore", "Dentist", lid),
        )
    else:
        row = fetchone(
            """
            INSERT INTO leads (
              workspace_id, campaign_id, name, category, city, email, phone, website,
              stage, score, tier, confidence, source, dedupe_key
            ) VALUES (
              1, %s, %s, %s, %s, %s, %s, %s, 'approved', 72, 'A', 0.80, 'test', %s
            ) RETURNING id
            """,
            (
                cid,
                "Dummy Dental Clinic",
                "Dentist",
                "Lahore",
                DUMMY_TO,
                "+923001112233",
                "https://example.com",
                f"dummydentalclinic|{DUMMY_TO}",
            ),
        )
        lid = int(row["id"])  # type: ignore
        execute(
            """
            INSERT INTO lead_signals (lead_id, channel, signal, value, verified)
            VALUES (%s,'website','no_pixel','true',true),
                   (%s,'email','email_found',%s,true)
            """,
            (lid, lid, DUMMY_TO),
        )
    # clear prior steps for clean test
    execute("DELETE FROM outreach_steps WHERE lead_id=%s", (lid,))
    execute(
        "DELETE FROM suppression WHERE workspace_id=1 AND email=%s",
        (DUMMY_TO,),
    )
    return lid


def wait_for_mail(before: set[str], timeout: float = 10.0) -> Path | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        files = {p.name for p in MAIL_DIR.glob("mail_*.eml")}
        new = files - before
        if new:
            name = sorted(new)[-1]
            return MAIL_DIR / name
        time.sleep(0.2)
    return None


def main() -> int:
    MAIL_DIR.mkdir(exist_ok=True)
    before = {p.name for p in MAIL_DIR.glob("mail_*.eml")}

    sender = ensure_sender()
    assert can_send(sender), "sender must be ready (address + verified)"
    print(f"[1] sender ready id={sender['id']} smtp={sender['smtp_host']}:{sender['smtp_port']}")

    # SMTP test email (Settings-equivalent)
    send_email(
        sender,
        DUMMY_TO,
        "Leadgensystem SMTP test",
        f"SMTP test from Leadgensystem.\n\n{sender['sender_name']}\n{sender['physical_address']}",
    )
    test_mail = wait_for_mail(before)
    assert test_mail, "SMTP test email not caught by dummy server"
    body = test_mail.read_text(encoding="utf-8")
    assert "SMTP test" in body
    assert "123 Demo Street" in body
    print(f"[2] SMTP test caught: {test_mail.name}")
    before = {p.name for p in MAIL_DIR.glob("mail_*.eml")}

    lid = ensure_lead(int(sender["id"]))
    created = enqueue_sequence(lid)
    assert created == 3, f"expected 3 steps, got {created}"
    steps = fetchall(
        "SELECT id, step, status, subject FROM outreach_steps WHERE lead_id=%s ORDER BY step",
        (lid,),
    )
    assert len(steps) == 3
    print(f"[3] sequence enqueued lead={lid} steps={[s['step'] for s in steps]}")

    approve_steps([int(s["id"]) for s in steps])
    step1 = fetchone(
        "SELECT id FROM outreach_steps WHERE lead_id=%s AND step=1",
        (lid,),
    )
    ok = send_step(int(step1["id"]))  # type: ignore
    assert ok, "send_step failed"
    sent = fetchone("SELECT status, subject FROM outreach_steps WHERE id=%s", (step1["id"],))
    assert sent and sent["status"] == "sent"
    nurture = wait_for_mail(before)
    assert nurture, "nurture email not caught"
    nurture_body = nurture.read_text(encoding="utf-8")
    assert "Dummy Dental Clinic" in nurture_body or "Unsubscribe" in nurture_body
    assert "Unsubscribe" in nurture_body
    assert "123 Demo Street" in nurture_body
    print(f"[4] nurture step1 sent + caught: {nurture.name}")
    print(f"    subject={sent['subject']}")

    token = make_token(1, DUMMY_TO)
    parsed = parse_token(token)
    assert parsed == (1, DUMMY_TO)
    suppress(1, DUMMY_TO, "unsubscribe")
    assert is_suppressed(1, DUMMY_TO)
    print(f"[5] unsubscribe token ok; suppressed {DUMMY_TO}")

    # second send must skip
    execute(
        "UPDATE outreach_steps SET status='approved', sent_at=NULL WHERE lead_id=%s AND step=2",
        (lid,),
    )
    step2 = fetchone(
        "SELECT id FROM outreach_steps WHERE lead_id=%s AND step=2",
        (lid,),
    )
    before2 = {p.name for p in MAIL_DIR.glob("mail_*.eml")}
    ok2 = send_step(int(step2["id"]))  # type: ignore
    assert ok2 is False
    st2 = fetchone("SELECT status, error FROM outreach_steps WHERE id=%s", (step2["id"],))
    assert st2 and st2["status"] == "skipped" and "suppress" in (st2["error"] or "").lower()
    assert wait_for_mail(before2, timeout=2.0) is None
    print("[6] suppressed send correctly skipped")

    print("\nE2E DUMMY MAIL: PASS")
    print(f"  recipient={DUMMY_TO}")
    print(f"  mails in {MAIL_DIR}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"\nE2E DUMMY MAIL: FAIL — {exc}")
        raise SystemExit(1)
