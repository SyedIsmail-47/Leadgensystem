"""Enrichment pipeline: crawl websites, validate, write signals."""
from __future__ import annotations

from typing import Any

from common.db import execute, fetchall, fetchone
from common.logging import get_logger
from enrich.validators import normalize_phone, validate_email
from scrapers.leads_repo import finish_run, start_run
from scrapers.website import crawl_website

log = get_logger("enrich.pipeline")


def _add_signal(
    lead_id: int,
    channel: str,
    signal: str,
    value: str | None,
    verified: bool,
) -> None:
    execute(
        """
        INSERT INTO lead_signals (lead_id, channel, signal, value, verified)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (lead_id, channel, signal, value, verified),
    )


def enrich_lead(lead: dict[str, Any]) -> bool:
    """Enrich one lead. Returns True if useful contact/signal found."""
    lead_id = int(lead["id"])
    useful = False

    # gmaps baseline signal
    _add_signal(lead_id, "gmaps", "listed", lead.get("gmaps_url"), True)

    phone_norm, phone_ok = normalize_phone(lead.get("phone"))
    if phone_norm:
        execute("UPDATE leads SET phone = %s WHERE id = %s", (phone_norm, lead_id))
        _add_signal(lead_id, "phone", "valid_phone", phone_norm, phone_ok)
        useful = useful or phone_ok

    website = lead.get("website")
    if not website:
        execute(
            "UPDATE leads SET stage = CASE WHEN stage = 'new' THEN 'enriched' ELSE stage END, updated_at = now() WHERE id = %s",
            (lead_id,),
        )
        return useful

    data = crawl_website(website)
    if data.get("error") and data["pages_fetched"] == 0:
        execute(
            "UPDATE leads SET stage = CASE WHEN stage = 'new' THEN 'enriched' ELSE stage END, updated_at = now() WHERE id = %s",
            (lead_id,),
        )
        return useful

    _add_signal(lead_id, "website", "crawled", website, True)

    best_email = None
    best_mx = False
    for em in data.get("emails") or []:
        norm, mx_ok = validate_email(em)
        if norm:
            _add_signal(lead_id, "email", "email_found", norm, mx_ok)
            if mx_ok and not best_mx:
                best_email, best_mx = norm, True
            elif best_email is None:
                best_email, best_mx = norm, mx_ok
    if best_email:
        execute("UPDATE leads SET email = %s WHERE id = %s", (best_email, lead_id))
        useful = True

    updates: dict[str, Any] = {}
    for field in ("facebook_url", "instagram_url", "linkedin_url", "whatsapp_link"):
        val = data.get(field)
        if val:
            updates[field] = val
            channel = "social" if field != "whatsapp_link" else "phone"
            _add_signal(lead_id, channel, field, val, True)
            useful = True

    if data.get("has_meta_pixel"):
        _add_signal(lead_id, "website", "has_pixel", "meta", True)
    if data.get("has_google_tag"):
        _add_signal(lead_id, "website", "has_google_tag", "gtag", True)
    if data.get("has_booking"):
        _add_signal(lead_id, "website", "has_booking", "true", True)
    if data.get("has_contact_form"):
        _add_signal(lead_id, "website", "has_contact_form", "true", True)
    if not data.get("has_https"):
        _add_signal(lead_id, "website", "no_https", "true", True)
    if data.get("has_viewport"):
        _add_signal(lead_id, "website", "mobile_viewport", "true", True)

    # opportunity gaps
    if not data.get("has_meta_pixel") and not data.get("has_google_tag"):
        _add_signal(lead_id, "website", "no_pixel", "true", True)
    if not data.get("has_booking"):
        _add_signal(lead_id, "website", "no_booking", "true", True)
    if not data.get("has_contact_form"):
        _add_signal(lead_id, "website", "no_contact_form", "true", True)

    if updates:
        sets = ", ".join(f"{k} = %s" for k in updates)
        execute(
            f"UPDATE leads SET {sets}, stage = 'enriched', updated_at = now() WHERE id = %s",
            (*updates.values(), lead_id),
        )
    else:
        execute(
            "UPDATE leads SET stage = 'enriched', updated_at = now() WHERE id = %s",
            (lead_id,),
        )
    return useful


def enrich_pending(workspace_id: int | None = None, limit: int = 50) -> dict[str, int]:
    params: list[Any] = []
    sql = """
        SELECT * FROM leads
        WHERE website IS NOT NULL AND website <> ''
          AND stage IN ('new', 'enriched')
          AND id NOT IN (
            SELECT lead_id FROM lead_signals WHERE channel = 'website' AND signal = 'crawled'
          )
    """
    if workspace_id is not None:
        sql += " AND workspace_id = %s"
        params.append(workspace_id)
    sql += " ORDER BY id ASC LIMIT %s"
    params.append(limit)

    leads = fetchall(sql, tuple(params))
    ws = workspace_id or (leads[0]["workspace_id"] if leads else 1)
    run_id = start_run(int(ws), "enrich_pending", None)
    enriched = 0
    with_contact = 0
    errors = 0

    for lead in leads:
        try:
            ok = enrich_lead(lead)
            enriched += 1
            if ok:
                with_contact += 1
        except Exception as exc:
            errors += 1
            log.exception("enrich failed lead=%s: %s", lead.get("id"), exc)

    finish_run(
        run_id,
        "ok" if errors == 0 else "ok_with_errors",
        found=enriched,
        errors=errors,
        log=f"enriched={enriched} with_contact={with_contact}",
    )
    return {"enriched": enriched, "with_contact": with_contact, "errors": errors}


def enrichment_rate(workspace_id: int = 1) -> float:
    row = fetchone(
        """
        SELECT
          COUNT(*) FILTER (WHERE website IS NOT NULL AND website <> '') AS with_site,
          COUNT(*) FILTER (
            WHERE website IS NOT NULL AND website <> ''
              AND (
                email IS NOT NULL
                OR facebook_url IS NOT NULL
                OR instagram_url IS NOT NULL
                OR linkedin_url IS NOT NULL
                OR whatsapp_link IS NOT NULL
                OR EXISTS (
                  SELECT 1 FROM lead_signals s
                  WHERE s.lead_id = leads.id AND s.channel IN ('email','social')
                )
              )
          ) AS filled
        FROM leads WHERE workspace_id = %s
        """,
        (workspace_id,),
    )
    if not row or not row["with_site"]:
        return 0.0
    return float(row["filled"]) / float(row["with_site"])
