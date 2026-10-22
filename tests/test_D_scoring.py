import pytest

from common.db import execute, fetchall, fetchone
from scoring.engine import score_lead
from scoring.rules import compute_confidence, evaluate_rules, tier_for


def _full_lead(**over):
    base = {
        "name": "Full",
        "category": "Dentist",
        "website": "https://x.com",
        "rating": 4.5,
        "review_count": 50,
        "city": "Lahore",
        "address": "Lahore",
        "email": "a@b.com",
        "phone": "+923001234567",
        "whatsapp_link": "https://wa.me/1",
        "facebook_url": "https://facebook.com/x",
    }
    base.update(over)
    return base


def _full_signals():
    return [
        {"channel": "gmaps", "signal": "listed", "verified": True},
        {"channel": "website", "signal": "no_pixel", "verified": True},
        {"channel": "website", "signal": "has_pixel", "verified": True},
        {"channel": "ads", "signal": "meta_ads", "verified": True},
        {"channel": "ads", "signal": "google_ads", "verified": True},
        {"channel": "email", "signal": "email_found", "verified": True},
        {"channel": "phone", "signal": "valid_phone", "verified": True},
        {"channel": "social", "signal": "facebook_url", "verified": True},
    ]


@pytest.mark.unit
def test_D1_all_rules_100_A():
    b = evaluate_rules(_full_lead(), _full_signals(), niche="dentist", location="Lahore")
    total = sum(x["points"] for x in b)
    assert total == 100
    assert tier_for(total, True) == "A"


@pytest.mark.unit
def test_D2_empty_lead_0_C():
    b = evaluate_rules({"name": "Only"}, [], niche=None, location=None)
    total = sum(x["points"] for x in b)
    assert total == 0
    assert tier_for(total, False) == "C"


@pytest.mark.unit
def test_D3_rating_threshold():
    low = evaluate_rules({"name": "n", "rating": 3.9}, [], niche=None, location="x")
    high = evaluate_rules({"name": "n", "rating": 4.0}, [], niche=None, location="x")
    assert next(r["points"] for r in low if r["rule"] == "rating_ge_4") == 0
    assert next(r["points"] for r in high if r["rule"] == "rating_ge_4") == 6


@pytest.mark.unit
def test_D4_reviews_threshold():
    low = evaluate_rules({"name": "n", "review_count": 19}, [], niche=None, location="x")
    high = evaluate_rules({"name": "n", "review_count": 20}, [], niche=None, location="x")
    assert next(r["points"] for r in low if r["rule"] == "reviews_ge_20") == 0
    assert next(r["points"] for r in high if r["rule"] == "reviews_ge_20") == 6


@pytest.mark.unit
def test_D5_tier_capped_without_contact():
    lead = _full_lead(email=None, phone=None, whatsapp_link=None, facebook_url=None, instagram_url=None, linkedin_url=None)
    signals = [
        {"channel": "website", "signal": "no_pixel", "verified": True},
        {"channel": "ads", "signal": "meta_ads", "verified": True},
        {"channel": "gmaps", "signal": "listed", "verified": True},
        {"channel": "website", "signal": "crawled", "verified": True},
    ]
    b = evaluate_rules(lead, signals, niche="dentist", location="Lahore")
    # remove intent google/social/email/phone/wa/pixel points by using subset
    total = sum(x["points"] for x in b)
    # Fit 40 + meta 15 = 55 if all fit true and meta
    assert total >= 45
    assert tier_for(total, False) == "C"


@pytest.mark.unit
def test_D6_tier_boundaries():
    assert tier_for(70, True) == "A"
    assert tier_for(69, True) == "B"
    assert tier_for(45, True) == "B"
    assert tier_for(44, True) == "C"


@pytest.mark.integration
def test_D7_score_idempotent(db):
    lead = fetchone(
        """
        INSERT INTO leads (workspace_id, name, website, email, phone, rating, review_count, city, category, dedupe_key, stage)
        VALUES (1,'S','https://x.com','a@b.com','+923001234567',4.5,50,'Lahore','Dentist','s|1','enriched')
        RETURNING id
        """
    )
    lid = lead["id"]
    execute(
        "INSERT INTO lead_signals (lead_id, channel, signal, verified) VALUES (%s,'email','email_found',true),(%s,'phone','valid_phone',true),(%s,'website','no_pixel',true)",
        (lid, lid, lid),
    )
    r1 = score_lead(lid)
    n1 = fetchone("SELECT COUNT(*) AS c FROM lead_scores WHERE lead_id=%s", (lid,))["c"]
    r2 = score_lead(lid)
    n2 = fetchone("SELECT COUNT(*) AS c FROM lead_scores WHERE lead_id=%s", (lid,))["c"]
    assert n1 == n2
    assert r1.score == r2.score


@pytest.mark.integration
def test_D8_per_campaign_weight_override(db):
    sp = fetchone(
        "INSERT INTO scoring_profiles (workspace_id, name, weights) VALUES (1,'ov',%s::jsonb) RETURNING id",
        ('{"meta_ads": 25}',),
    )
    camp = fetchone(
        "INSERT INTO campaigns (workspace_id, name, niche, location, scoring_profile_id) VALUES (1,'c','dentist','Lahore',%s) RETURNING id",
        (sp["id"],),
    )
    lead = fetchone(
        """
        INSERT INTO leads (workspace_id, campaign_id, name, website, email, phone, dedupe_key, stage)
        VALUES (1,%s,'L','https://x.com','a@b.com','+923001234567','l|1','enriched') RETURNING id
        """,
        (camp["id"],),
    )
    execute(
        "INSERT INTO lead_signals (lead_id, channel, signal, verified) VALUES (%s,'ads','meta_ads',true),(%s,'email','email_found',true),(%s,'phone','valid_phone',true)",
        (lead["id"], lead["id"], lead["id"]),
    )
    with_default = score_lead(int(lead["id"]), weights=None)
    # re-score with explicit default vs override already loaded from campaign
    # campaign has meta 25; default 15 → +10
    assert any(b["rule"] == "meta_ads" and b["points"] == 25 for b in with_default.breakdown)


@pytest.mark.unit
def test_D9_confidence():
    two = [
        {"channel": "gmaps", "signal": "listed", "verified": True},
        {"channel": "website", "signal": "crawled", "verified": True},
    ]
    assert compute_confidence(two) == 0.4
    five = two + [
        {"channel": "social", "signal": "facebook_url", "verified": True},
        {"channel": "ads", "signal": "meta_ads", "verified": True},
        {"channel": "email", "signal": "email_found", "verified": True},
    ]
    assert compute_confidence(five) == 1.0


@pytest.mark.integration
def test_D10_breakdown_sums_to_score(db):
    lead = fetchone(
        """
        INSERT INTO leads (workspace_id, name, website, email, phone, rating, review_count, city, category, dedupe_key, stage)
        VALUES (1,'S','https://x.com','a@b.com','+923001234567',4.5,50,'Lahore','Dentist','s|d10','enriched')
        RETURNING id
        """
    )
    execute(
        "INSERT INTO lead_signals (lead_id, channel, signal, verified) VALUES (%s,'email','email_found',true),(%s,'phone','valid_phone',true),(%s,'website','no_pixel',true),(%s,'gmaps','listed',true)",
        (lead["id"], lead["id"], lead["id"], lead["id"]),
    )
    res = score_lead(int(lead["id"]))
    rows = fetchall("SELECT points FROM lead_scores WHERE lead_id=%s", (lead["id"],))
    assert sum(r["points"] for r in rows) == res.score
    assert fetchone("SELECT score FROM leads WHERE id=%s", (lead["id"],))["score"] == res.score
