"""Lead upsert helpers."""
from __future__ import annotations

from typing import Any

from common.db import execute, fetchone
from common.models import LeadDraft
from scrapers.dedupe import dedupe_key


def upsert_lead(
    workspace_id: int,
    campaign_id: int | None,
    draft: LeadDraft,
) -> int:
    key = dedupe_key(draft.name, draft.phone, draft.website)
    existing = fetchone(
        "SELECT id FROM leads WHERE workspace_id = %s AND dedupe_key = %s",
        (workspace_id, key),
    )
    if existing:
        execute(
            """
            UPDATE leads SET
              campaign_id = COALESCE(%s, campaign_id),
              category = COALESCE(%s, category),
              address = COALESCE(%s, address),
              city = COALESCE(%s, city),
              phone = COALESCE(%s, phone),
              website = COALESCE(%s, website),
              email = COALESCE(%s, email),
              gmaps_url = COALESCE(%s, gmaps_url),
              rating = COALESCE(%s, rating),
              review_count = COALESCE(%s, review_count),
              source = COALESCE(%s, source),
              updated_at = now()
            WHERE id = %s
            """,
            (
                campaign_id,
                draft.category,
                draft.address,
                draft.city,
                draft.phone,
                draft.website,
                draft.email,
                draft.gmaps_url,
                draft.rating,
                draft.review_count,
                draft.source,
                existing["id"],
            ),
        )
        return int(existing["id"])

    row = fetchone(
        """
        INSERT INTO leads (
          workspace_id, campaign_id, name, category, address, city, phone, website,
          email, gmaps_url, rating, review_count, source, dedupe_key, stage
        ) VALUES (
          %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'new'
        ) RETURNING id
        """,
        (
            workspace_id,
            campaign_id,
            draft.name,
            draft.category,
            draft.address,
            draft.city,
            draft.phone,
            draft.website,
            draft.email,
            draft.gmaps_url,
            draft.rating,
            draft.review_count,
            draft.source,
            key,
        ),
    )
    return int(row["id"])  # type: ignore[index]


def start_run(workspace_id: int, job: str, campaign_id: int | None = None) -> int:
    row = fetchone(
        """
        INSERT INTO runs (workspace_id, job, campaign_id, status)
        VALUES (%s, %s, %s, 'running') RETURNING id
        """,
        (workspace_id, job, campaign_id),
    )
    return int(row["id"])  # type: ignore[index]


def finish_run(
    run_id: int,
    status: str,
    found: int = 0,
    errors: int = 0,
    log: str = "",
) -> None:
    execute(
        """
        UPDATE runs SET status = %s, found = %s, errors = %s, log = %s, finished_at = now()
        WHERE id = %s
        """,
        (status, found, errors, log, run_id),
    )


def append_run_log(run_id: int, message: str) -> None:
    execute(
        "UPDATE runs SET log = COALESCE(log, '') || %s WHERE id = %s",
        (message + "\n", run_id),
    )


def passes_filters(draft: LeadDraft, filters: dict[str, Any] | None) -> bool:
    if not filters:
        return True
    min_rating = filters.get("min_rating")
    if min_rating is not None and (draft.rating is None or draft.rating < float(min_rating)):
        return False
    min_reviews = filters.get("min_reviews")
    if min_reviews is not None and (
        draft.review_count is None or draft.review_count < int(min_reviews)
    ):
        return False
    if filters.get("must_website") and not draft.website:
        return False
    if filters.get("must_phone") and not draft.phone:
        return False
    excludes = filters.get("exclude_keywords") or []
    hay = " ".join(
        x for x in [draft.name, draft.category, draft.address] if x
    ).lower()
    for kw in excludes:
        if kw and str(kw).lower() in hay:
            return False
    return True


def location_label(country: str | None, city: str, area: str | None = None) -> str:
    parts = [p for p in [area, city, country] if p]
    return ", ".join(parts)
