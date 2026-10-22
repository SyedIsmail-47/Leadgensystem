from pathlib import Path

import pytest

from common.db import fetchall, fetchone
from enrich.pipeline import enrich_lead
from scrapers.website import analyze_html, crawl_website

FIX = Path(__file__).parent / "fixtures"


def _insert_lead(website: str) -> int:
    row = fetchone(
        """
        INSERT INTO leads (workspace_id, name, website, dedupe_key, stage)
        VALUES (1, 'T', %s, %s, 'new') RETURNING id
        """,
        (website, f"t|{website}"),
    )
    return int(row["id"])


@pytest.mark.integration
def test_C1_site_full_signals(db):
    html = (FIX / "site_full.html").read_text(encoding="utf-8")
    data = analyze_html(html)
    assert data["emails"]
    assert data["facebook_url"] and "sharer" not in data["facebook_url"]
    assert data["instagram_url"]
    assert data["linkedin_url"]
    assert data["whatsapp_link"]
    assert data["has_meta_pixel"]
    assert data["has_google_tag"]
    assert data["has_booking"]
    assert data["has_contact_form"]

    lid = _insert_lead("https://full.example")
    enrich_lead(
        {
            "id": lid,
            "website": "https://full.example",
            "phone": None,
            "gmaps_url": "https://maps.example/x",
        }
    )
    # inject crawl via analyze path: call enrich with fetcher by temporarily patching
    from unittest.mock import patch

    with patch("enrich.pipeline.crawl_website", return_value={**data, "pages_fetched": 1, "error": None}):
        enrich_lead(
            fetchone("SELECT * FROM leads WHERE id=%s", (lid,))
        )
    signals = {(r["channel"], r["signal"]) for r in fetchall("SELECT channel, signal FROM lead_signals WHERE lead_id=%s", (lid,))}
    assert ("website", "has_pixel") in signals
    assert ("website", "has_google_tag") in signals
    assert ("website", "has_booking") in signals
    assert ("social", "facebook_url") in signals or ("social", "instagram_url") in signals


@pytest.mark.integration
def test_C2_site_bare_gap(db):
    data = analyze_html((FIX / "site_bare.html").read_text(encoding="utf-8"))
    assert not data["has_meta_pixel"]
    assert not data["has_booking"]
    assert not data["has_contact_form"]
    lid = _insert_lead("https://bare.example")
    from unittest.mock import patch

    with patch(
        "enrich.pipeline.crawl_website",
        return_value={**data, "pages_fetched": 1, "error": None, "has_https": True},
    ):
        enrich_lead(fetchone("SELECT * FROM leads WHERE id=%s", (lid,)))
    sigs = {r["signal"] for r in fetchall("SELECT signal FROM lead_signals WHERE lead_id=%s", (lid,))}
    assert "no_pixel" in sigs
    assert "no_booking" in sigs
    assert "no_contact_form" in sigs


@pytest.mark.unit
def test_C3_meta_pixel_both_forms():
    assert analyze_html("<script>fbq('track');</script>")["has_meta_pixel"]
    assert analyze_html('<script src="https://connect.facebook.net/x.js"></script>')["has_meta_pixel"]


@pytest.mark.unit
def test_C4_google_tag_both_forms():
    assert analyze_html("<script>gtag('config','G');</script>")["has_google_tag"]
    assert analyze_html('<script src="https://www.googletagmanager.com/gtag/js"></script>')["has_google_tag"]


@pytest.mark.unit
def test_C5_booking_widget():
    assert analyze_html((FIX / "site_booking.html").read_text(encoding="utf-8"))["has_booking"]


@pytest.mark.unit
def test_C6_whatsapp_formats():
    data = analyze_html((FIX / "site_wa.html").read_text(encoding="utf-8"))
    assert data["whatsapp_link"]
    assert "wa.me" in data["whatsapp_link"] or "api.whatsapp.com" in data["whatsapp_link"]


@pytest.mark.unit
def test_C7_social_excludes_sharer():
    data = analyze_html((FIX / "site_full.html").read_text(encoding="utf-8"))
    assert data["facebook_url"]
    assert "sharer" not in data["facebook_url"]


@pytest.mark.integration
def test_C8_timeout_soft_fail(db):
    lid = _insert_lead("https://down.example")

    def boom(_url: str):
        raise TimeoutError("timeout")

    from unittest.mock import patch

    with patch("enrich.pipeline.crawl_website", return_value={"error": "timeout", "pages_fetched": 0}):
        enrich_lead(fetchone("SELECT * FROM leads WHERE id=%s", (lid,)))
    row = fetchone("SELECT enrich_error, stage FROM leads WHERE id=%s", (lid,))
    assert row["enrich_error"]
    # second lead continues
    lid2 = _insert_lead("https://ok.example")
    html = (FIX / "site_bare.html").read_text(encoding="utf-8")
    data = analyze_html(html)
    with patch("enrich.pipeline.crawl_website", return_value={**data, "pages_fetched": 1, "error": None, "has_https": True}):
        enrich_lead(fetchone("SELECT * FROM leads WHERE id=%s", (lid2,)))
    assert fetchone("SELECT stage FROM leads WHERE id=%s", (lid2,))["stage"] == "enriched"


@pytest.mark.unit
def test_C9_crawl_limits_same_domain():
    pages = {"https://ex.com": (FIX / "site_full.html").read_text(encoding="utf-8")}
    for i in range(10):
        pages[f"https://ex.com/contact{i}"] = "<html><body>contact</body></html>"

    def fetcher(u: str):
        return 200, pages.get(u, "<html><a href='/contact'>c</a><a href='/about'>a</a></html>")

    result = crawl_website("https://ex.com", max_pages=5, fetcher=fetcher)
    assert result["pages_fetched"] <= 5
    for u in result.get("fetched_urls") or []:
        assert u.startswith("https://ex.com")


@pytest.mark.integration
def test_C10_enrich_idempotent_signals(db):
    lid = _insert_lead("https://idem.example")
    data = analyze_html((FIX / "site_full.html").read_text(encoding="utf-8"))
    from unittest.mock import patch

    with patch("enrich.pipeline.crawl_website", return_value={**data, "pages_fetched": 1, "error": None, "has_https": True}):
        enrich_lead(fetchone("SELECT * FROM leads WHERE id=%s", (lid,)))
        n1 = fetchone("SELECT COUNT(*) AS c FROM lead_signals WHERE lead_id=%s", (lid,))["c"]
        enrich_lead(fetchone("SELECT * FROM leads WHERE id=%s", (lid,)))
        n2 = fetchone("SELECT COUNT(*) AS c FROM lead_signals WHERE lead_id=%s", (lid,))["c"]
    assert n1 == n2
