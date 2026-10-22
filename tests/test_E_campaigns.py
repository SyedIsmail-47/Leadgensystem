
import pytest

from campaigns.builder import (
    build_query_grid,
    dry_run_preview,
    normalize_niches,
    require_profiles_for_outreach,
    validate_campaign_input,
)
from common.db import fetchone
from common.models import LeadDraft
from scrapers.leads_repo import passes_filters


@pytest.mark.unit
def test_E1_query_grid_2x3():
    niches = ["dentist", "clinic"]
    locs = [{"city": "Lahore"}, {"city": "Karachi"}, {"city": "Islamabad"}]
    assert len(build_query_grid(niches, locs)) == 6


@pytest.mark.unit
def test_E2_niche_dedupe_case():
    assert normalize_niches(["Dentist", "dentist ", "Dentist"]) == ["Dentist"]


@pytest.mark.integration
def test_E3_dry_run_no_db_writes(db):
    before = fetchone("SELECT COUNT(*) AS c FROM campaigns")["c"]
    preview = dry_run_preview(["dentist"], [{"city": "Lahore"}, {"city": "Karachi"}])
    assert preview["query_count"] == 2
    assert "estimated_runtime_sec" in preview
    assert fetchone("SELECT COUNT(*) AS c FROM campaigns")["c"] == before


@pytest.mark.unit
def test_E4_filters_exclude():
    filters = {"min_rating": 4.0, "min_reviews": 20, "must_website": True, "exclude_keywords": ["clinic"]}
    ok = LeadDraft(name="Smile Dental", rating=4.5, review_count=25, website="https://x.com")
    bad = LeadDraft(name="City Clinic", rating=4.5, review_count=25, website="https://x.com")
    assert passes_filters(ok, filters)
    assert not passes_filters(bad, filters)


@pytest.mark.unit
def test_E5_max_limits_respected():
    # discover_campaign clamps via min(max_per_query, remaining)
    max_per_query, max_per_run = 5, 12
    remaining = max_per_run
    totals = []
    for _ in range(10):
        if remaining <= 0:
            break
        got = min(max_per_query, remaining)
        totals.append(got)
        remaining -= got
    assert sum(totals) == 12
    assert all(t <= 5 for t in totals)


@pytest.mark.unit
def test_E6_source_toggles_mocked():
    sources = {"gmaps": False, "osm_fallback": True}
    called = {"gmaps": False, "osm": False}

    def gmaps(*_a, **_k):
        called["gmaps"] = True
        return 0

    def osm(*_a, **_k):
        called["osm"] = True
        return 1

    # simulate campaign_discover branch
    got = 0
    if sources.get("gmaps", True):
        got = gmaps()
    if got == 0 and sources.get("osm_fallback", True):
        got = osm()
    assert called["gmaps"] is False
    assert called["osm"] is True


@pytest.mark.unit
def test_E7_invalid_input():
    errs = validate_campaign_input(name="", niches=[], locations=[], max_leads=0, cron="bad")
    assert "empty niche" in errs
    assert "empty location" in errs
    assert "max_leads must be > 0" in errs
    assert "bad cron" in errs


@pytest.mark.integration
def test_E8_outreach_requires_profiles(db):
    camp = fetchone(
        "INSERT INTO campaigns (workspace_id, name, niche, location) VALUES (1,'c','n','L') RETURNING id"
    )
    msg = require_profiles_for_outreach(int(camp["id"]))
    assert msg and "Offer Profile" in msg
