"""Campaign query grid, validation, dry-run."""
from __future__ import annotations

import re
from typing import Any

from common.db import fetchone


def normalize_niches(niches: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for n in niches:
        key = re.sub(r"\s+", " ", (n or "").strip().lower())
        if not key or key in seen:
            continue
        seen.add(key)
        out.append((n or "").strip())
    return out


def build_query_grid(niches: list[str], locations: list[dict[str, Any]]) -> list[tuple[str, str]]:
    niches_n = normalize_niches(niches)
    queries: list[tuple[str, str]] = []
    for niche in niches_n:
        for loc in locations:
            parts = [p for p in [loc.get("area"), loc.get("city"), loc.get("country")] if p]
            label = ", ".join(parts) if parts else str(loc.get("city") or "")
            if label:
                queries.append((niche, label))
    return queries


def dry_run_preview(
    niches: list[str],
    locations: list[dict[str, Any]],
    *,
    seconds_per_query: float = 45.0,
) -> dict[str, Any]:
    queries = build_query_grid(niches, locations)
    return {
        "query_count": len(queries),
        "queries": queries,
        "estimated_runtime_sec": round(len(queries) * seconds_per_query, 1),
    }


def validate_campaign_input(
    *,
    name: str,
    niches: list[str],
    locations: list[dict[str, Any]],
    max_leads: int,
    cron: str | None = None,
) -> list[str]:
    errors: list[str] = []
    if not (name or "").strip():
        errors.append("name required")
    if not normalize_niches(niches):
        errors.append("empty niche")
    if not locations or not any((l.get("city") or "").strip() for l in locations):
        errors.append("empty location")
    if max_leads is None or int(max_leads) <= 0:
        errors.append("max_leads must be > 0")
    if cron:
        parts = cron.split()
        if len(parts) not in (5, 6):
            errors.append("bad cron")
    return errors


def require_profiles_for_outreach(campaign_id: int) -> str | None:
    row = fetchone(
        "SELECT offer_profile_id, sender_profile_id FROM campaigns WHERE id=%s",
        (campaign_id,),
    )
    if not row:
        return "campaign not found"
    if not row.get("offer_profile_id"):
        return "Offer Profile required before Start outreach"
    if not row.get("sender_profile_id"):
        return "Sender Profile required before Start outreach"
    sender = fetchone(
        "SELECT physical_address, smtp_verified_at FROM sender_profiles WHERE id=%s",
        (row["sender_profile_id"],),
    )
    if not sender or not (sender.get("physical_address") or "").strip() or not sender.get("smtp_verified_at"):
        return "Sender Profile must have physical address and verified SMTP"
    return None


CRON_RE = re.compile(r"^(\S+\s+){4}\S+$")
