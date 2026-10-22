"""Parse Google Maps HTML fixtures (no Playwright)."""
from __future__ import annotations

import re
from typing import Any

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from common.models import LeadDraft


def is_blocked_html(html: str) -> bool:
    return "unusual traffic" in html.lower()


def parse_place_html(html: str, *, gmaps_url: str | None = None) -> LeadDraft | None:
    if is_blocked_html(html):
        return None
    tree = HTMLParser(html)
    name = None
    for h in tree.css("div[role='main'] h1, h1"):
        text = (h.text() or "").strip()
        if text and text.lower() not in {"results", "result", "overview"}:
            name = text
            break
    if not name:
        return None

    category = None
    for b in tree.css("button"):
        if "category" in (b.attributes.get("jsaction") or ""):
            category = (b.text() or "").strip() or None
            break

    address = None
    phone = None
    website = None
    for b in tree.css("button"):
        item = b.attributes.get("data-item-id") or ""
        if item == "address":
            address = (b.text() or "").strip() or None
        if item.startswith("phone:tel:"):
            phone = item.replace("phone:tel:", "", 1)
    for a in tree.css('a[data-item-id="authority"]'):
        website = a.attributes.get("href")

    rating = None
    review_count = None
    for span in tree.css("div.F7nice span"):
        ah = span.attributes.get("aria-hidden")
        if ah == "true":
            m = re.search(r"(\d+[.,]\d+)", (span.text() or "").replace(",", "."))
            if m:
                rating = float(m.group(1))
        label = span.attributes.get("aria-label") or ""
        if "review" in label.lower():
            m = re.search(r"([\d,]+)", label)
            if m:
                review_count = int(m.group(1).replace(",", ""))

    city = None
    if address and "," in address:
        parts = [p.strip() for p in address.split(",")]
        city = parts[-1] if parts else None

    return LeadDraft(
        name=name,
        category=category,
        address=address,
        city=city,
        phone=phone,
        website=website,
        gmaps_url=gmaps_url,
        rating=rating,
        review_count=review_count,
        source="gmaps",
    )


def parse_feed_names(html: str) -> list[str]:
    tree = HTMLParser(html)
    names: list[str] = []
    for a in tree.css('div[role="feed"] a[href*="/maps/place/"]'):
        t = (a.text() or "").strip()
        if t:
            names.append(t)
    return names


def delay_seconds(lo: float, hi: float, rng: Any) -> float:
    return float(rng.uniform(lo, hi))
