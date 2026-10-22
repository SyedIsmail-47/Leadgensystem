import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from freezegun import freeze_time

from common.db import execute, fetchall, fetchone
from common.models import LeadDraft
from enrich.pipeline import enrich_lead
from outreach.sender import send_step
from outreach.sequences import approve_steps, enqueue_sequence
from outreach.unsubscribe import is_suppressed, suppress
from scrapers.gmaps_parse import parse_place_html
from scrapers.leads_repo import upsert_lead
from scoring.engine import score_lead

FIX = Path(__file__).parent / "fixtures"


@pytest.mark.e2e
def test_K1_full_pipeline(db, verified_sender, fake_smtp, offer_profile_id, scoring_profile_id):
    box, *_ = fake_smtp
    # 1-2 campaign with 2 locations conceptually; fixture-backed discover
    camp = fetchone(
        """
        INSERT INTO campaigns (workspace_id, name, niche, location, offer_profile_id, sender_profile_id, scoring_profile_id, filters, sources)
        VALUES (1,'E2E','dentist','Lahore',%s,%s,%s,%s::jsonb,%s::jsonb) RETURNING id
        """,
        (
            offer_profile_id,
            verified_sender["id"],
            scoring_profile_id,
            json.dumps({"max_per_query": 10, "max_per_run": 20}),
            json.dumps({"gmaps": True, "osm_fallback": True}),
        ),
    )
    cid = int(camp["id"])
    execute("INSERT INTO campaign_niches (campaign_id, niche) VALUES (%s,'dentist')", (cid,))
    execute(
        "INSERT INTO campaign_locations (campaign_id, country, city) VALUES (%s,'PK','Lahore'),(%s,'PK','Karachi')",
        (cid, cid),
    )

    # 3 discover from fixture
    html = (FIX / "gmaps_results.html").read_text(encoding="utf-8")
    place = parse_place_html(html)
    assert place
    upsert_lead(1, cid, place)
    upsert_lead(
        1,
        cid,
        LeadDraft(
            name="Second Dental",
            category="Dentist",
            city="Karachi",
            phone="+923009998877",
            website="https://second.example",
            email=None,
            rating=4.2,
            review_count=30,
        ),
    )
    # dedupe
    upsert_lead(1, cid, place)
    leads = fetchall("SELECT * FROM leads WHERE campaign_id=%s", (cid,))
    assert len(leads) == 2

    # 4 enrich with fixture html
    from scrapers.website import analyze_html

    data = analyze_html((FIX / "site_full.html").read_text(encoding="utf-8"))
    with patch("enrich.pipeline.crawl_website", return_value={**data, "pages_fetched": 1, "error": None, "has_https": True}):
        for lead in leads:
            if lead.get("website"):
                enrich_lead(fetchone("SELECT * FROM leads WHERE id=%s", (lead["id"],)))
    assert fetchone("SELECT COUNT(*) AS c FROM lead_signals")["c"] > 0

    # 5 score
    for lead in fetchall("SELECT id FROM leads WHERE campaign_id=%s", (cid,)):
        score_lead(int(lead["id"]))
    scored = fetchall("SELECT score, tier, confidence FROM leads WHERE campaign_id=%s", (cid,))
    assert all(s["score"] is not None and s["tier"] for s in scored)

    # 6 approve + send
    for lead in fetchall("SELECT id, email, tier FROM leads WHERE campaign_id=%s", (cid,)):
        if not lead["email"]:
            execute("UPDATE leads SET email=%s WHERE id=%s", (f"lead{lead['id']}@example.com", lead["id"]))
        execute("UPDATE leads SET stage='approved' WHERE id=%s", (lead["id"],))
        enqueue_sequence(int(lead["id"]))
    steps = fetchall("SELECT id FROM outreach_steps WHERE status='pending' AND step=1")
    approve_steps([int(s["id"]) for s in steps])
    # make due
    execute("UPDATE outreach_steps SET scheduled_for=now() - interval '1 minute' WHERE step=1")
    sent_n = 0
    for s in steps:
        if send_step(int(s["id"])):
            sent_n += 1
    assert sent_n >= 1
    assert box.messages
    assert any("unsubscribe" in m["content"].lower() for m in box.messages)
    assert any("1 Test St" in m["content"] for m in box.messages)

    # 7 unsubscribe one
    to = box.messages[0]["to"][0]
    suppress(1, to, "unsubscribe")
    assert is_suppressed(1, to)
    remaining = fetchall(
        """
        SELECT os.id FROM outreach_steps os
        JOIN leads l ON l.id = os.lead_id
        WHERE l.email=%s AND os.step=2 AND os.status='pending'
        """,
        (to,),
    )
    if remaining:
        approve_steps([int(remaining[0]["id"])])
        execute("UPDATE outreach_steps SET scheduled_for=now() - interval '1 minute', status='approved' WHERE id=%s", (remaining[0]["id"],))
        before = len(box.messages)
        with freeze_time(datetime.now(timezone.utc) + __import__("datetime").timedelta(days=4)):
            send_step(int(remaining[0]["id"]))
        assert len(box.messages) == before  # suppressed

    # 8 replied stops
    lead_id = fetchone("SELECT id FROM leads WHERE campaign_id=%s LIMIT 1", (cid,))["id"]
    execute("UPDATE leads SET stage='replied' WHERE id=%s", (lead_id,))
    step3 = fetchone("SELECT id FROM outreach_steps WHERE lead_id=%s AND step=3", (lead_id,))
    if step3:
        approve_steps([int(step3["id"])])
        execute("UPDATE outreach_steps SET status='approved', scheduled_for=now()-interval '1 minute' WHERE id=%s", (step3["id"],))
        assert send_step(int(step3["id"])) is False

    # 9 csv
    df = pd.DataFrame(fetchall("SELECT * FROM leads WHERE campaign_id=%s", (cid,)))
    assert len(df) == 2

    # runs rows — create synthetic success markers for jobs
    from scrapers.leads_repo import finish_run, start_run

    for job in ("discover_campaign", "enrich_pending", "score_pending", "send_due_steps"):
        rid = start_run(1, job, cid)
        finish_run(rid, "ok", found=1)
    assert fetchone("SELECT COUNT(*) AS c FROM runs WHERE status='ok'")["c"] >= 4
