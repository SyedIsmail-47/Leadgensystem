"""OpenStreetMap Overpass API fallback discovery."""
from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

import httpx

from common.logging import get_logger
from common.models import LeadDraft
from scrapers.leads_repo import (
    append_run_log,
    finish_run,
    passes_filters,
    start_run,
    upsert_lead,
)

log = get_logger("scrapers.osm")

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Map free-text niches to OSM amenity/shop tags
NICHE_TAGS: dict[str, list[str]] = {
    "dentist": ['"amenity"="dentist"'],
    "gym": ['"leisure"="fitness_centre"', '"leisure"="sports_centre"'],
    "restaurant": ['"amenity"="restaurant"'],
    "cafe": ['"amenity"="cafe"'],
    "hotel": ['"tourism"="hotel"'],
    "real estate": ['"office"="estate_agent"'],
    "lawyer": ['"office"="lawyer"'],
    "clinic": ['"amenity"="clinic"', '"amenity"="doctors"'],
}


def _tags_for_niche(niche: str) -> list[str]:
    key = niche.strip().lower()
    for k, tags in NICHE_TAGS.items():
        if k in key:
            return tags
    # generic name search via Around + name regex is heavy; use shop/amenity name match
    safe = niche.replace('"', "")
    return [f'"name"~"{safe}",i']


def discover_osm(
    niche: str,
    location: str,
    max_leads: int = 20,
    run_id: int | None = None,
    workspace_id: int = 1,
    campaign_id: int | None = None,
    filters: dict[str, Any] | None = None,
) -> int:
    own_run = run_id is None
    if own_run:
        run_id = start_run(workspace_id, "discover_osm", campaign_id)
    assert run_id is not None

    found = 0
    errors = 0
    log_buf: list[str] = [f"osm query: {niche} in {location}"]
    tags = _tags_for_niche(niche)
    tag_filters = "".join(
        f'node[{t}](area.searchArea);way[{t}](area.searchArea);'
        for t in tags
    )
    query = f"""
    [out:json][timeout:60];
    area[name="{location.split(',')[0].strip()}"]->.searchArea;
    (
      {tag_filters}
    );
    out center tags {max_leads};
    """

    try:
        with httpx.Client(timeout=70.0) as client:
            resp = client.post(OVERPASS_URL, data={"data": query})
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        log.exception("overpass failed")
        if own_run:
            finish_run(run_id, "failed", found=0, errors=1, log=str(exc))
        return 0

    elements = data.get("elements") or []
    for el in elements:
        if found >= max_leads:
            break
        tags_map = el.get("tags") or {}
        name = tags_map.get("name")
        if not name:
            continue
        phone = tags_map.get("phone") or tags_map.get("contact:phone")
        website = tags_map.get("website") or tags_map.get("contact:website")
        city = tags_map.get("addr:city") or location.split(",")[0].strip()
        address_parts = [
            tags_map.get("addr:housenumber"),
            tags_map.get("addr:street"),
            city,
        ]
        address = ", ".join(p for p in address_parts if p)
        draft = LeadDraft(
            name=name,
            category=niche,
            address=address or None,
            city=city,
            phone=phone,
            website=website,
            gmaps_url=None,
            source="osm",
        )
        if not passes_filters(draft, filters):
            continue
        try:
            upsert_lead(workspace_id, campaign_id, draft)
            found += 1
            log_buf.append(f"saved: {name}")
        except Exception as exc:
            errors += 1
            log_buf.append(f"error: {exc}")

    status = "ok" if found else "empty"
    if own_run:
        finish_run(run_id, status, found=found, errors=errors, log="\n".join(log_buf))
    else:
        append_run_log(run_id, "\n".join(log_buf))
    log.info("osm discover found=%s", found)
    return found


def geocode_hint(location: str) -> str:
    return quote_plus(location)
