"""Nurture sequence creation and rendering."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from common.config import get_settings
from common.db import execute, fetchall, fetchone
from common.logging import get_logger
from outreach.unsubscribe import make_token

log = get_logger("outreach.sequences")

TEMPLATE_DIR = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(enabled_extensions=()),
)


def gap_hook_for_lead(lead_id: int, offer: dict[str, Any] | None) -> str:
    signals = fetchall(
        "SELECT signal FROM lead_signals WHERE lead_id = %s", (lead_id,)
    )
    sig_names = {s["signal"] for s in signals}
    rules = []
    if offer:
        rules = offer.get("gap_hook_rules") or []
        if isinstance(rules, str):
            rules = json.loads(rules)
    for rule in rules:
        if rule.get("signal") in sig_names:
            return rule.get("sentence") or ""
    if "no_pixel" in sig_names:
        return "noticed you run no tracking on your site"
    if "no_booking" in sig_names:
        return "noticed visitors cannot book online"
    return "saw an opportunity to improve how new customers find you"


def _render_from_offer(
    offer: dict[str, Any] | None,
    step: int,
    ctx: dict[str, Any],
) -> tuple[str, str]:
    templates = (offer or {}).get("templates") or {}
    if isinstance(templates, str):
        templates = json.loads(templates)
    key = f"step{step}"
    block = templates.get(key) or {}
    if block.get("subject") and block.get("body"):
        subj = _env.from_string(block["subject"]).render(**ctx)
        body = _env.from_string(block["body"]).render(**ctx)
        # ensure footer compliance fields
        if "{{ physical_address }}" not in (block.get("body") or "") and ctx.get("physical_address"):
            body += (
                f"\n\n{ctx.get('sender_name')}\n{ctx.get('company') or ''}\n"
                f"{ctx.get('physical_address')}\nUnsubscribe: {ctx.get('unsubscribe_url')}"
            )
        return subj, body
    tmpl = _env.get_template(f"step{step}.j2")
    body = tmpl.render(**ctx)
    subjects = {
        1: f"Quick idea for {ctx.get('name')} in {ctx.get('city')}",
        2: f"Case note for {ctx.get('category')} in {ctx.get('city')}",
        3: "Worth a quick look?",
    }
    return subjects[step], body


def enqueue_sequence(lead_id: int) -> int:
    lead = fetchone("SELECT * FROM leads WHERE id = %s", (lead_id,))
    if not lead:
        raise ValueError("lead not found")
    existing = fetchone(
        "SELECT 1 AS ok FROM outreach_steps WHERE lead_id = %s LIMIT 1", (lead_id,)
    )
    if existing:
        return 0

    offer = None
    sender = None
    if lead.get("campaign_id"):
        camp = fetchone("SELECT * FROM campaigns WHERE id = %s", (lead["campaign_id"],))
        if camp and camp.get("offer_profile_id"):
            offer = fetchone(
                "SELECT * FROM offer_profiles WHERE id = %s", (camp["offer_profile_id"],)
            )
        if camp and camp.get("sender_profile_id"):
            sender = fetchone(
                "SELECT * FROM sender_profiles WHERE id = %s", (camp["sender_profile_id"],)
            )

    email = lead.get("email")
    if not email:
        return 0

    token = make_token(int(lead["workspace_id"]), email)
    unsub = f"{get_settings().base_url}/unsubscribe?token={token}"
    ctx = {
        "name": lead.get("name") or "",
        "category": lead.get("category") or "business",
        "city": lead.get("city") or "",
        "gap_hook": gap_hook_for_lead(lead_id, offer),
        "sender_name": (sender or {}).get("sender_name") or "Team",
        "company": (sender or {}).get("company") or "",
        "physical_address": (sender or {}).get("physical_address") or "",
        "unsubscribe_url": unsub,
    }

    now = datetime.now(timezone.utc)
    offsets = {1: 0, 2: 3, 3: 7}
    created = 0
    for step in (1, 2, 3):
        subject, body = _render_from_offer(offer, step, ctx)
        scheduled = now + timedelta(days=offsets[step])
        execute(
            """
            INSERT INTO outreach_steps (
              workspace_id, lead_id, step, channel, status, subject, body, scheduled_for
            ) VALUES (%s,%s,%s,'email','pending',%s,%s,%s)
            """,
            (lead["workspace_id"], lead_id, step, subject, body, scheduled),
        )
        created += 1
    execute(
        "UPDATE leads SET stage='approved', updated_at=now() WHERE id=%s AND stage NOT IN ('contacted','replied','won','lost')",
        (lead_id,),
    )
    return created


def approve_steps(step_ids: list[int]) -> int:
    if not step_ids:
        return 0
    return execute(
        "UPDATE outreach_steps SET status='approved' WHERE id = ANY(%s) AND status='pending'",
        (step_ids,),
    )


def approve_tier_a(workspace_id: int) -> int:
    rows = fetchall(
        """
        SELECT os.id FROM outreach_steps os
        JOIN leads l ON l.id = os.lead_id
        WHERE os.workspace_id = %s AND os.status = 'pending' AND l.tier = 'A'
        """,
        (workspace_id,),
    )
    ids = [int(r["id"]) for r in rows]
    return approve_steps(ids)
