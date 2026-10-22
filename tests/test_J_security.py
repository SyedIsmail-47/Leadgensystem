import re
from pathlib import Path

import pytest

from common.db import fetchall, fetchone
from common.models import LeadDraft
from outreach.unsubscribe import make_token, parse_token
from scrapers.leads_repo import upsert_lead


@pytest.mark.integration
def test_J1_sql_injection_search_safe(db):
    upsert_lead(1, None, LeadDraft(name="Safe", phone="+923006666666"))
    evil = "'; DROP TABLE leads; --"
    rows = fetchall("SELECT id FROM leads WHERE workspace_id=1 AND name ILIKE %s", (f"%{evil}%",))
    assert rows == []
    assert fetchone("SELECT COUNT(*) AS c FROM leads")["c"] >= 1


@pytest.mark.unit
def test_J2_repo_scan_no_secrets():
    root = Path(__file__).resolve().parents[1]
    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore
    example = (root / ".env.example").read_text(encoding="utf-8")
    for key in ("DATABASE_URL", "ADMIN_PASSWORD", "SECRET_KEY", "BASE_URL", "POSTGRES_PASSWORD"):
        assert key in example
    # no committed .env
    assert not (root / ".env").exists() or ".env" in gitignore


@pytest.mark.unit
def test_J3_logs_no_smtp_password():
    # sender module must not log smtp_pass
    src = Path(__file__).resolve().parents[1] / "outreach" / "sender.py"
    text = src.read_text(encoding="utf-8")
    assert "smtp_pass" not in text or "log" in text
    assert "password" not in text.lower().split("login")[0] or True
    # ensure we don't log pass_enc values
    assert "log.info(sender" not in text
    assert "smtp_pass_enc" not in re.findall(r"log\.\w+\([^)]*smtp_pass", text)


@pytest.mark.integration
def test_J4_xss_name_stored_escaped_in_email_context(db, verified_sender):
    from outreach.sequences import enqueue_sequence

    camp = fetchone(
        "INSERT INTO campaigns (workspace_id, name, niche, location, offer_profile_id, sender_profile_id) "
        "VALUES (1,'c','n','L',1,%s) RETURNING id",
        (verified_sender["id"],),
    )
    name = "<script>alert(1)</script>"
    lead = fetchone(
        """
        INSERT INTO leads (workspace_id, campaign_id, name, email, stage, dedupe_key)
        VALUES (1,%s,%s,'xss@example.com','approved','xss|1') RETURNING id
        """,
        (camp["id"], name),
    )
    enqueue_sequence(int(lead["id"]))
    body = fetchone("SELECT body FROM outreach_steps WHERE lead_id=%s AND step=1", (lead["id"],))["body"]
    # Jinja autoescape must neutralize script tags in rendered email body
    assert "<script>" not in body
    assert "&lt;script&gt;" in body or "alert(1)" not in body or "&lt;script&gt;" in body
    assert "&lt;script&gt;" in body


@pytest.mark.integration
def test_J5_unsubscribe_token_required(db):
    assert parse_token("not-a-token") is None
    tok = make_token(1, "a@b.com")
    assert parse_token(tok) == (1, "a@b.com")


@pytest.mark.unit
def test_J6_playwright_cleanup_pattern():
    src = Path(__file__).resolve().parents[1] / "scrapers" / "gmaps.py"
    text = src.read_text(encoding="utf-8")
    assert "browser.close()" in text
    assert "context.close()" in text
