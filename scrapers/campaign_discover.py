"""Expand campaign niche × location grid and run discovery."""
from __future__ import annotations

import json

from common.db import fetchall, fetchone
from common.logging import get_logger
from scrapers.gmaps import discover as discover_gmaps
from scrapers.leads_repo import finish_run, location_label, start_run
from scrapers.osm import discover_osm

log = get_logger("scrapers.campaign_discover")


def dry_run_query_count(campaign_id: int) -> int:
    niches = fetchall(
        "SELECT niche FROM campaign_niches WHERE campaign_id = %s", (campaign_id,)
    )
    locs = fetchall(
        "SELECT country, city, area FROM campaign_locations WHERE campaign_id = %s",
        (campaign_id,),
    )
    if not niches or not locs:
        # fallback to legacy columns
        camp = fetchone("SELECT niche, location FROM campaigns WHERE id = %s", (campaign_id,))
        if camp and camp.get("niche") and camp.get("location"):
            return 1
        return 0
    return len(niches) * len(locs)


def discover_campaign(campaign_id: int) -> int:
    camp = fetchone("SELECT * FROM campaigns WHERE id = %s", (campaign_id,))
    if not camp:
        raise ValueError(f"campaign {campaign_id} not found")

    workspace_id = int(camp["workspace_id"])
    filters = camp.get("filters") or {}
    if isinstance(filters, str):
        filters = json.loads(filters)
    sources = camp.get("sources") or {}
    if isinstance(sources, str):
        sources = json.loads(sources)

    use_gmaps = sources.get("gmaps", True)
    use_osm = sources.get("osm_fallback", True)
    max_per_query = int(filters.get("max_per_query") or camp.get("max_leads") or 50)
    max_per_run = int(filters.get("max_per_run") or 150)

    niches = fetchall(
        "SELECT niche FROM campaign_niches WHERE campaign_id = %s", (campaign_id,)
    )
    locs = fetchall(
        "SELECT country, city, area, radius_km FROM campaign_locations WHERE campaign_id = %s",
        (campaign_id,),
    )

    queries: list[tuple[str, str]] = []
    if niches and locs:
        for n in niches:
            for loc in locs:
                label = location_label(loc.get("country"), loc["city"], loc.get("area"))
                queries.append((n["niche"], label))
    elif camp.get("niche") and camp.get("location"):
        queries.append((camp["niche"], camp["location"]))

    run_id = start_run(workspace_id, "discover_campaign", campaign_id)
    total = 0
    errors = 0

    try:
        for niche, location in queries:
            if total >= max_per_run:
                break
            remaining = max_per_run - total
            limit = min(max_per_query, remaining)
            got = 0
            if use_gmaps:
                try:
                    got = discover_gmaps(
                        niche,
                        location,
                        max_leads=limit,
                        run_id=run_id,
                        workspace_id=workspace_id,
                        campaign_id=campaign_id,
                        filters=filters,
                    )
                except Exception:
                    errors += 1
                    log.exception("gmaps failed for %s / %s", niche, location)
                    got = 0
            if got == 0 and use_osm:
                try:
                    got = discover_osm(
                        niche,
                        location,
                        max_leads=limit,
                        run_id=run_id,
                        workspace_id=workspace_id,
                        campaign_id=campaign_id,
                        filters=filters,
                    )
                except Exception:
                    errors += 1
                    log.exception("osm failed for %s / %s", niche, location)
            total += got

        status = "ok" if total else "empty"
        # preserve blocked if set mid-run
        row = fetchone("SELECT status FROM runs WHERE id = %s", (run_id,))
        if row and row["status"] == "blocked":
            status = "blocked"
        finish_run(run_id, status, found=total, errors=errors)
    except Exception as exc:
        finish_run(run_id, "failed", found=total, errors=errors + 1, log=str(exc))
        raise

    return total
