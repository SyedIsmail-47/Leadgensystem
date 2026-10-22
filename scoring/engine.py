"""Score leads and persist breakdown."""
from __future__ import annotations

import json
from typing import Any

from common.db import execute, fetchall, fetchone
from common.logging import get_logger
from common.models import ScoreResult
from scrapers.leads_repo import finish_run, start_run
from scoring.rules import (
    DEFAULT_WEIGHTS,
    compute_confidence,
    evaluate_rules,
    tier_for,
)

log = get_logger("scoring.engine")


def _load_weights(campaign_id: int | None) -> dict[str, int]:
    if not campaign_id:
        return dict(DEFAULT_WEIGHTS)
    row = fetchone(
        """
        SELECT sp.weights
        FROM campaigns c
        LEFT JOIN scoring_profiles sp ON sp.id = c.scoring_profile_id
        WHERE c.id = %s
        """,
        (campaign_id,),
    )
    if not row or not row.get("weights"):
        return dict(DEFAULT_WEIGHTS)
    weights = row["weights"]
    if isinstance(weights, str):
        weights = json.loads(weights)
    return {**DEFAULT_WEIGHTS, **{k: int(v) for k, v in weights.items()}}


def score_lead(lead_id: int, weights: dict[str, int] | None = None) -> ScoreResult:
    lead = fetchone("SELECT * FROM leads WHERE id = %s", (lead_id,))
    if not lead:
        raise ValueError(f"lead {lead_id} not found")

    signals = fetchall("SELECT * FROM lead_signals WHERE lead_id = %s", (lead_id,))
    niche = None
    location = None
    if lead.get("campaign_id"):
        camp = fetchone(
            "SELECT niche, location FROM campaigns WHERE id = %s",
            (lead["campaign_id"],),
        )
        if camp:
            niche, location = camp.get("niche"), camp.get("location")
        niches = fetchall(
            "SELECT niche FROM campaign_niches WHERE campaign_id = %s LIMIT 1",
            (lead["campaign_id"],),
        )
        if niches:
            niche = niches[0]["niche"]

    w = weights or _load_weights(lead.get("campaign_id"))
    breakdown = evaluate_rules(lead, signals, niche=niche, location=location, weights=w)
    score = min(100, sum(int(b["points"]) for b in breakdown))
    confidence = compute_confidence(signals)
    has_reachable = bool(lead.get("email") or lead.get("phone") or lead.get("whatsapp_link"))
    tier = tier_for(score, has_reachable)

    execute("DELETE FROM lead_scores WHERE lead_id = %s", (lead_id,))
    for b in breakdown:
        execute(
            "INSERT INTO lead_scores (lead_id, rule, points, detail) VALUES (%s,%s,%s,%s)",
            (lead_id, b["rule"], b["points"], b["detail"]),
        )
    execute(
        """
        UPDATE leads SET score = %s, tier = %s, confidence = %s,
          stage = CASE WHEN stage IN ('new','enriched') THEN 'scored' ELSE stage END,
          updated_at = now()
        WHERE id = %s
        """,
        (score, tier, confidence, lead_id),
    )
    return ScoreResult(score=score, tier=tier, confidence=confidence, breakdown=breakdown)


def score_pending(workspace_id: int | None = None, limit: int = 200) -> int:
    params: list[Any] = []
    sql = """
        SELECT id FROM leads
        WHERE stage IN ('enriched', 'scored', 'new')
    """
    if workspace_id is not None:
        sql += " AND workspace_id = %s"
        params.append(workspace_id)
    sql += " ORDER BY id ASC LIMIT %s"
    params.append(limit)
    rows = fetchall(sql, tuple(params))
    ws = workspace_id or 1
    run_id = start_run(int(ws), "score_pending", None)
    n = 0
    errors = 0
    for row in rows:
        try:
            score_lead(int(row["id"]))
            n += 1
        except Exception:
            errors += 1
            log.exception("score failed lead=%s", row["id"])
    finish_run(run_id, "ok", found=n, errors=errors)
    return n
