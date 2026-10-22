import pytest

from common.auth import verify_password
from common.db import execute, fetchall, fetchone
from common.schema import apply_schema
from scrapers.leads_repo import upsert_lead
from common.models import LeadDraft

REQUIRED_TABLES = {
    "users",
    "workspaces",
    "campaigns",
    "leads",
    "lead_signals",
    "lead_scores",
    "outreach_steps",
    "suppression",
    "runs",
    "settings",
    "offer_profiles",
    "sender_profiles",
    "scoring_profiles",
}


@pytest.mark.integration
def test_A1_all_tables_exist(db):
    rows = fetchall(
        """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema='public' AND table_type='BASE TABLE'
        """
    )
    names = {r["table_name"] for r in rows}
    missing = REQUIRED_TABLES - names
    assert not missing, missing


@pytest.mark.integration
def test_A2_init_sql_idempotent(test_dsn):
    apply_schema(test_dsn, reset=False)
    apply_schema(test_dsn, reset=False)  # second apply must not error
    assert fetchone("SELECT COUNT(*) AS c FROM workspaces")["c"] >= 1


@pytest.mark.integration
def test_A3_owned_tables_have_workspace_id(db):
    owned = [
        "users",
        "settings",
        "offer_profiles",
        "sender_profiles",
        "scoring_profiles",
        "campaigns",
        "campaign_presets",
        "leads",
        "outreach_steps",
        "suppression",
        "runs",
    ]
    for table in owned:
        row = fetchone(
            """
            SELECT 1 AS ok FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s AND column_name='workspace_id'
            """,
            (table,),
        )
        assert row, f"{table} missing workspace_id"


@pytest.mark.integration
def test_A4_seed_admin_hashed(db):
    users = fetchall("SELECT * FROM users")
    assert len(users) == 1
    assert fetchone("SELECT COUNT(*) AS c FROM workspaces")["c"] == 1
    u = users[0]
    assert u["password_hash"] != "test-admin-pass"
    assert verify_password("test-admin-pass", u["password_hash"])
    assert u["password_hash"].startswith("$2")


@pytest.mark.integration
def test_A5_campaign_delete_cascades(db):
    camp = fetchone(
        "INSERT INTO campaigns (workspace_id, name, niche, location) VALUES (1,'c','n','L') RETURNING id"
    )
    cid = camp["id"]
    lead = fetchone(
        """
        INSERT INTO leads (workspace_id, campaign_id, name, dedupe_key)
        VALUES (1,%s,'X','x|1') RETURNING id
        """,
        (cid,),
    )
    lid = lead["id"]
    execute(
        "INSERT INTO lead_signals (lead_id, channel, signal, value, verified) VALUES (%s,'gmaps','listed','u',true)",
        (lid,),
    )
    execute(
        "INSERT INTO lead_scores (lead_id, rule, points) VALUES (%s,'has_website',8)",
        (lid,),
    )
    execute(
        "INSERT INTO outreach_steps (workspace_id, lead_id, step, status) VALUES (1,%s,1,'pending')",
        (lid,),
    )
    execute("DELETE FROM campaigns WHERE id=%s", (cid,))
    assert fetchone("SELECT COUNT(*) AS c FROM leads WHERE id=%s", (lid,))["c"] == 0
    assert fetchone("SELECT COUNT(*) AS c FROM lead_signals WHERE lead_id=%s", (lid,))["c"] == 0
    assert fetchone("SELECT COUNT(*) AS c FROM lead_scores WHERE lead_id=%s", (lid,))["c"] == 0
    assert fetchone("SELECT COUNT(*) AS c FROM outreach_steps WHERE lead_id=%s", (lid,))["c"] == 0


@pytest.mark.integration
def test_A6_dedupe_key_unique(db):
    d = LeadDraft(name="Smile", phone="+923001234567", website=None)
    a = upsert_lead(1, None, d)
    b = upsert_lead(1, None, d)
    assert a == b
    assert fetchone("SELECT COUNT(*) AS c FROM leads")["c"] == 1
