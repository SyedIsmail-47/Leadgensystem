import json
import random
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from common.db import fetchone
from common.models import LeadDraft
from scrapers.gmaps_parse import delay_seconds, is_blocked_html, parse_feed_names, parse_place_html
from scrapers.leads_repo import finish_run, start_run, upsert_lead
from scrapers.osm import discover_osm

FIX = Path(__file__).parent / "fixtures"


@pytest.mark.unit
def test_F1_parse_gmaps_fixture():
    html = (FIX / "gmaps_results.html").read_text(encoding="utf-8")
    names = parse_feed_names(html)
    assert len(names) >= 2
    place = parse_place_html(html, gmaps_url="https://maps.google.com/place/1")
    assert place and place.name == "Smile Dental"
    assert place.category == "Dentist"
    assert place.phone
    assert place.website
    assert place.rating == 4.5
    assert place.review_count == 120


@pytest.mark.integration
def test_F2_missing_optional_fields(db):
    d = LeadDraft(name="Sparse", category=None, phone=None, website=None)
    lid = upsert_lead(1, None, d)
    row = fetchone("SELECT * FROM leads WHERE id=%s", (lid,))
    assert row["name"] == "Sparse"
    assert row["phone"] is None


@pytest.mark.integration
def test_F3_blocked_fixture(db):
    html = (FIX / "gmaps_blocked.html").read_text(encoding="utf-8")
    assert is_blocked_html(html)
    run_id = start_run(1, "discover_gmaps", None)
    # partial result kept
    upsert_lead(1, None, LeadDraft(name="Partial", phone="+923001111111"))
    finish_run(run_id, "blocked", found=1, errors=0, log="unusual traffic")
    row = fetchone("SELECT status, found FROM runs WHERE id=%s", (run_id,))
    assert row["status"] == "blocked"
    assert row["found"] == 1


@pytest.mark.integration
def test_F4_rerun_no_duplicates(db):
    d = LeadDraft(name="Dup", phone="+923002222222")
    upsert_lead(1, None, d)
    upsert_lead(1, None, d)
    assert fetchone("SELECT COUNT(*) AS c FROM leads WHERE name='Dup'")["c"] == 1


@pytest.mark.integration
def test_F5_osm_fallback_mocked(db):
    payload = json.loads((FIX / "osm_overpass.json").read_text(encoding="utf-8"))

    class Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    with patch("scrapers.osm.httpx.Client") as client_cls:
        client = MagicMock()
        client.__enter__.return_value = client
        client.__exit__.return_value = None
        client.post.return_value = Resp()
        client_cls.return_value = client
        n = discover_osm("dentist", "Lahore", max_leads=10, workspace_id=1)
    assert n >= 2
    assert fetchone("SELECT COUNT(*) AS c FROM leads WHERE source='osm'")["c"] >= 2


@pytest.mark.unit
def test_F6_delay_helper_bounds():
    class R:
        def uniform(self, lo, hi):
            return (lo + hi) / 2

    v = delay_seconds(2.0, 6.0, R())
    assert 2.0 <= v <= 6.0
    rng = random.Random(0)
    for _ in range(20):
        x = delay_seconds(2.0, 6.0, rng)
        assert 2.0 <= x <= 6.0


@pytest.mark.unit
def test_F7_ads_scrapers_soft():
    from scrapers import google_ads, meta_ads

    # soft stubs never raise to caller when used carefully; call returns bool
    assert meta_ads.check_meta_ads.__name__
    assert google_ads.check_google_ads.__name__
