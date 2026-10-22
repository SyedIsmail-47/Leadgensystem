from scoring.rules import compute_confidence, evaluate_rules, tier_for


def test_evaluate_rules_website_and_rating():
    lead = {
        "name": "Smile Dental",
        "category": "Dentist",
        "website": "https://example.com",
        "rating": 4.5,
        "review_count": 25,
        "city": "Lahore",
        "email": "a@example.com",
        "phone": "+923001234567",
    }
    signals = [
        {"channel": "website", "signal": "no_pixel", "verified": True},
        {"channel": "email", "signal": "email_found", "verified": True},
        {"channel": "phone", "signal": "valid_phone", "verified": True},
        {"channel": "gmaps", "signal": "listed", "verified": True},
    ]
    breakdown = evaluate_rules(lead, signals, niche="dentist", location="Lahore")
    by_rule = {b["rule"]: b["points"] for b in breakdown}
    assert by_rule["has_website"] == 8
    assert by_rule["rating_ge_4"] == 6
    assert by_rule["reviews_ge_20"] == 6
    assert by_rule["opportunity_gap"] == 6
    total = sum(b["points"] for b in breakdown)
    assert total > 40


def test_tier_and_cap():
    assert tier_for(80, True) == "A"
    assert tier_for(50, True) == "B"
    assert tier_for(80, False) == "C"


def test_confidence():
    signals = [
        {"channel": "gmaps", "signal": "listed", "verified": True},
        {"channel": "website", "signal": "crawled", "verified": True},
        {"channel": "email", "signal": "email_found", "verified": True},
    ]
    assert compute_confidence(signals) == 0.6
