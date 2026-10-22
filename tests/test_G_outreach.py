
import pytest
from freezegun import freeze_time

from common.db import execute, fetchall, fetchone
from outreach.sender import send_due_steps, send_step
from outreach.sequences import approve_steps, enqueue_sequence, gap_hook_for_lead
from outreach.unsubscribe import is_suppressed, make_token, parse_token, suppress


def _lead(db, email="lead@example.com", **kw):
    row = fetchone(
        """
        INSERT INTO leads (workspace_id, campaign_id, name, category, city, email, phone, website, stage, dedupe_key)
        VALUES (1,%s,'Clinic','Dentist','Lahore',%s,'+923001234567','https://c.example','approved',%s)
        RETURNING id
        """,
        (
            kw.get("campaign_id"),
            email,
            f"{email}|{kw.get('campaign_id')}",
        ),
    )
    return int(row["id"])


@pytest.mark.integration
def test_G1_no_sender_sends_nothing(db, fake_smtp):
    box, port, _ = fake_smtp
    camp = fetchone(
        "INSERT INTO campaigns (workspace_id, name, niche, location) VALUES (1,'c','n','L') RETURNING id"
    )
    lid = _lead(db, campaign_id=camp["id"])
    enqueue_sequence(lid)
    execute("UPDATE outreach_steps SET status='approved', scheduled_for=now() - interval '1 hour'")
    n = send_due_steps(limit=10)
    assert n == 0
    assert box.messages == []


@pytest.mark.integration
def test_G2_pending_not_sent(db, verified_sender, fake_smtp):
    box, port, _ = fake_smtp
    camp = fetchone(
        "INSERT INTO campaigns (workspace_id, name, niche, location, offer_profile_id, sender_profile_id) "
        "VALUES (1,'c','n','L',1,%s) RETURNING id",
        (verified_sender["id"],),
    )
    lid = _lead(db, campaign_id=camp["id"])
    enqueue_sequence(lid)
    n = send_due_steps()
    assert n == 0
    assert box.messages == []


@pytest.mark.integration
def test_G3_approved_step1_rendered(db, verified_sender, fake_smtp):
    box, *_ = fake_smtp
    camp = fetchone(
        "INSERT INTO campaigns (workspace_id, name, niche, location, offer_profile_id, sender_profile_id) "
        "VALUES (1,'c','dentist','Lahore',1,%s) RETURNING id",
        (verified_sender["id"],),
    )
    lid = _lead(db, campaign_id=camp["id"])
    execute(
        "INSERT INTO lead_signals (lead_id, channel, signal, verified) VALUES (%s,'website','no_pixel',true)",
        (lid,),
    )
    enqueue_sequence(lid)
    step = fetchone("SELECT id, subject, body FROM outreach_steps WHERE lead_id=%s AND step=1", (lid,))
    approve_steps([int(step["id"])])
    assert send_step(int(step["id"]))
    assert len(box.messages) == 1
    msg = box.messages[0]["content"]
    assert "Clinic" in msg
    assert "{{" not in msg
    assert "From:" in msg or "QA Sender" in msg


@pytest.mark.integration
def test_G4_footer_fields(db, verified_sender, fake_smtp):
    box, *_ = fake_smtp
    camp = fetchone(
        "INSERT INTO campaigns (workspace_id, name, niche, location, offer_profile_id, sender_profile_id) "
        "VALUES (1,'c','n','L',1,%s) RETURNING id",
        (verified_sender["id"],),
    )
    lid = _lead(db, campaign_id=camp["id"])
    enqueue_sequence(lid)
    step = fetchone("SELECT id, body FROM outreach_steps WHERE lead_id=%s AND step=1", (lid,))
    approve_steps([int(step["id"])])
    send_step(int(step["id"]))
    body = box.messages[0]["content"]
    assert "QA Sender" in body
    assert "1 Test St" in body
    assert "unsubscribe" in body.lower()


@pytest.mark.integration
def test_G5_step_timing_freezegun(db, verified_sender, fake_smtp):
    box, *_ = fake_smtp
    camp = fetchone(
        "INSERT INTO campaigns (workspace_id, name, niche, location, offer_profile_id, sender_profile_id) "
        "VALUES (1,'c','n','L',1,%s) RETURNING id",
        (verified_sender["id"],),
    )
    lid = _lead(db, campaign_id=camp["id"])
    with freeze_time("2026-01-01 10:00:00"):
        enqueue_sequence(lid)
        steps = fetchall("SELECT id, step, scheduled_for FROM outreach_steps WHERE lead_id=%s ORDER BY step", (lid,))
        approve_steps([int(s["id"]) for s in steps])
        assert send_step(int(steps[0]["id"]))
        assert send_step(int(steps[1]["id"])) is False  # not due
    with freeze_time("2026-01-04 10:00:00"):
        assert send_step(int(steps[1]["id"]))
    with freeze_time("2026-01-08 10:00:00"):
        assert send_step(int(steps[2]["id"]))
    assert len(box.messages) == 3


@pytest.mark.integration
def test_G6_suppressed_skipped(db, verified_sender, fake_smtp):
    box, *_ = fake_smtp
    camp = fetchone(
        "INSERT INTO campaigns (workspace_id, name, niche, location, offer_profile_id, sender_profile_id) "
        "VALUES (1,'c','n','L',1,%s) RETURNING id",
        (verified_sender["id"],),
    )
    lid = _lead(db, email="sup@example.com", campaign_id=camp["id"])
    suppress(1, "sup@example.com")
    enqueue_sequence(lid)
    step = fetchone("SELECT id FROM outreach_steps WHERE lead_id=%s AND step=1", (lid,))
    approve_steps([int(step["id"])])
    assert send_step(int(step["id"])) is False
    st = fetchone("SELECT status, error FROM outreach_steps WHERE id=%s", (step["id"],))
    assert st["status"] == "skipped"
    assert box.messages == []


@pytest.mark.integration
def test_G7_unsubscribe_token(db):
    tok = make_token(1, "u@example.com")
    assert parse_token(tok) == (1, "u@example.com")
    assert parse_token(tok + "x") is None
    suppress(1, "u@example.com", "unsubscribe")
    assert is_suppressed(1, "u@example.com")


@pytest.mark.integration
def test_G8_after_unsub_remaining_skipped(db, verified_sender, fake_smtp):
    box, *_ = fake_smtp
    camp = fetchone(
        "INSERT INTO campaigns (workspace_id, name, niche, location, offer_profile_id, sender_profile_id) "
        "VALUES (1,'c','n','L',1,%s) RETURNING id",
        (verified_sender["id"],),
    )
    lid = _lead(db, email="u2@example.com", campaign_id=camp["id"])
    enqueue_sequence(lid)
    steps = fetchall("SELECT id, step FROM outreach_steps WHERE lead_id=%s ORDER BY step", (lid,))
    approve_steps([int(s["id"]) for s in steps])
    send_step(int(steps[0]["id"]))
    suppress(1, "u2@example.com")
    execute(
        "UPDATE outreach_steps SET scheduled_for=now() - interval '1 minute' WHERE id=%s",
        (steps[1]["id"],),
    )
    assert send_step(int(steps[1]["id"])) is False
    assert fetchone("SELECT status FROM outreach_steps WHERE id=%s", (steps[1]["id"],))["status"] == "skipped"


@pytest.mark.integration
def test_G9_replied_stops(db, verified_sender, fake_smtp):
    camp = fetchone(
        "INSERT INTO campaigns (workspace_id, name, niche, location, offer_profile_id, sender_profile_id) "
        "VALUES (1,'c','n','L',1,%s) RETURNING id",
        (verified_sender["id"],),
    )
    lid = _lead(db, email="r@example.com", campaign_id=camp["id"])
    enqueue_sequence(lid)
    steps = fetchall("SELECT id FROM outreach_steps WHERE lead_id=%s ORDER BY step", (lid,))
    approve_steps([int(s["id"]) for s in steps])
    execute("UPDATE leads SET stage='replied' WHERE id=%s", (lid,))
    assert send_step(int(steps[0]["id"])) is False
    assert fetchone("SELECT status FROM outreach_steps WHERE id=%s", (steps[0]["id"],))["status"] == "skipped"


@pytest.mark.integration
def test_G10_daily_limit(db, verified_sender, fake_smtp):
    box, *_ = fake_smtp
    execute("UPDATE sender_profiles SET daily_limit=3 WHERE id=%s", (verified_sender["id"],))
    camp = fetchone(
        "INSERT INTO campaigns (workspace_id, name, niche, location, offer_profile_id, sender_profile_id) "
        "VALUES (1,'c','n','L',1,%s) RETURNING id",
        (verified_sender["id"],),
    )
    step_ids = []
    for i in range(5):
        lid = _lead(db, email=f"d{i}@example.com", campaign_id=camp["id"])
        enqueue_sequence(lid)
        s = fetchone("SELECT id FROM outreach_steps WHERE lead_id=%s AND step=1", (lid,))
        step_ids.append(int(s["id"]))
    approve_steps(step_ids)
    sent = 0
    for sid in step_ids:
        if send_step(sid):
            sent += 1
    assert sent == 3
    assert len(box.messages) == 3


@pytest.mark.integration
def test_G11_sending_window(db, verified_sender, fake_smtp):
    box, *_ = fake_smtp
    execute(
        "UPDATE sender_profiles SET send_window_start=9, send_window_end=17, timezone='Asia/Karachi' WHERE id=%s",
        (verified_sender["id"],),
    )
    camp = fetchone(
        "INSERT INTO campaigns (workspace_id, name, niche, location, offer_profile_id, sender_profile_id) "
        "VALUES (1,'c','n','L',1,%s) RETURNING id",
        (verified_sender["id"],),
    )
    lid = _lead(db, email="win@example.com", campaign_id=camp["id"])
    enqueue_sequence(lid)
    step = fetchone("SELECT id FROM outreach_steps WHERE lead_id=%s AND step=1", (lid,))
    approve_steps([int(step["id"])])
    # sender window check uses UTC hour currently — set window impossible
    execute("UPDATE sender_profiles SET send_window_start=10, send_window_end=11 WHERE id=%s", (verified_sender["id"],))
    with freeze_time("2026-01-01 22:00:00"):
        assert send_step(int(step["id"])) is False
    assert box.messages == []


@pytest.mark.integration
def test_G12_smtp_failure(db, verified_sender, fake_smtp):
    box, port, handler = fake_smtp
    handler.reject = True
    camp = fetchone(
        "INSERT INTO campaigns (workspace_id, name, niche, location, offer_profile_id, sender_profile_id) "
        "VALUES (1,'c','n','L',1,%s) RETURNING id",
        (verified_sender["id"],),
    )
    lid = _lead(db, email="fail@example.com", campaign_id=camp["id"])
    enqueue_sequence(lid)
    step = fetchone("SELECT id FROM outreach_steps WHERE lead_id=%s AND step=1", (lid,))
    approve_steps([int(step["id"])])
    assert send_step(int(step["id"])) is False
    st = fetchone("SELECT status, error FROM outreach_steps WHERE id=%s", (step["id"],))
    assert st["status"] == "failed"
    assert st["error"]


@pytest.mark.integration
def test_G13_no_email_skipped(db, verified_sender):
    camp = fetchone(
        "INSERT INTO campaigns (workspace_id, name, niche, location, offer_profile_id, sender_profile_id) "
        "VALUES (1,'c','n','L',1,%s) RETURNING id",
        (verified_sender["id"],),
    )
    row = fetchone(
        """
        INSERT INTO leads (workspace_id, campaign_id, name, phone, whatsapp_link, stage, dedupe_key)
        VALUES (1,%s,'NoMail','+923001234567','https://wa.me/923001234567','approved','nomail|1')
        RETURNING id
        """,
        (camp["id"],),
    )
    # enqueue requires email — create step manually
    execute(
        "INSERT INTO outreach_steps (workspace_id, lead_id, step, status, subject, body) VALUES (1,%s,1,'approved','s','b')",
        (row["id"],),
    )
    step = fetchone("SELECT id FROM outreach_steps WHERE lead_id=%s", (row["id"],))
    assert send_step(int(step["id"])) is False
    assert fetchone("SELECT status FROM outreach_steps WHERE id=%s", (step["id"],))["status"] == "skipped"
    assert fetchone("SELECT whatsapp_link FROM leads WHERE id=%s", (row["id"],))["whatsapp_link"]


@pytest.mark.integration
def test_G14_gap_hook(db):
    lid = _lead(db, email="gap@example.com", campaign_id=None)
    execute(
        "INSERT INTO lead_signals (lead_id, channel, signal, verified) VALUES (%s,'website','no_pixel',true)",
        (lid,),
    )
    offer = fetchone("SELECT * FROM offer_profiles LIMIT 1")
    hook = gap_hook_for_lead(lid, offer)
    assert "tracking" in hook.lower() or "pixel" in hook.lower() or "noticed" in hook.lower()


@pytest.mark.integration
def test_G15_offer_template_edit(db, verified_sender):
    execute(
        """
        UPDATE offer_profiles SET templates = %s::jsonb WHERE id=1
        """,
        (
            '{"step1":{"subject":"HELLO {{name}}","body":"BODY {{city}}\\n{{sender_name}}\\n{{physical_address}}\\n{{unsubscribe_url}}"}}',
        ),
    )
    camp = fetchone(
        "INSERT INTO campaigns (workspace_id, name, niche, location, offer_profile_id, sender_profile_id) "
        "VALUES (1,'c','n','L',1,%s) RETURNING id",
        (verified_sender["id"],),
    )
    lid = _lead(db, email="tmpl@example.com", campaign_id=camp["id"])
    enqueue_sequence(lid)
    step = fetchone("SELECT subject, body FROM outreach_steps WHERE lead_id=%s AND step=1", (lid,))
    assert step["subject"].startswith("HELLO ")
    assert "Lahore" in step["body"]
    assert "{{" not in step["body"]
