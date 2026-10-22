"""Google Maps discovery scraper (Playwright)."""
from __future__ import annotations

import random
import re
import time
from typing import Any
from urllib.parse import quote_plus

from common.logging import get_logger
from common.models import LeadDraft
from scrapers.leads_repo import (
    append_run_log,
    finish_run,
    passes_filters,
    start_run,
    upsert_lead,
)

log = get_logger("scrapers.gmaps")

SELECTORS: dict[str, str] = {
    "feed": 'div[role="feed"]',
    "result_links": 'div[role="feed"] a[href*="/maps/place/"]',
    "name": "h1",
    "category": 'button[jsaction*="category"]',
    "address": 'button[data-item-id="address"]',
    "phone": 'button[data-item-id^="phone:tel:"]',
    "website": 'a[data-item-id="authority"]',
    "rating": 'div.F7nice span[aria-hidden="true"]',
    "reviews": 'div.F7nice span[aria-label*="review"]',
    "unusual": "text=unusual traffic",
}


def _delay(lo: float = 2.0, hi: float = 6.0) -> None:
    time.sleep(random.uniform(lo, hi))


def _parse_rating(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r"(\d+[.,]\d+)", text.replace(",", "."))
    return float(m.group(1)) if m else None


def _parse_reviews(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"([\d,]+)", text)
    return int(m.group(1).replace(",", "")) if m else None


def _extract_place(page: Any) -> LeadDraft | None:
    try:
        name_el = page.locator(SELECTORS["name"]).first
        name = name_el.inner_text(timeout=5000).strip()
    except Exception:
        return None
    if not name:
        return None

    def safe_text(sel: str) -> str | None:
        try:
            loc = page.locator(sel).first
            if loc.count() == 0:
                return None
            return loc.inner_text(timeout=1500).strip() or None
        except Exception:
            return None

    def safe_attr(sel: str, attr: str) -> str | None:
        try:
            loc = page.locator(sel).first
            if loc.count() == 0:
                return None
            return loc.get_attribute(attr, timeout=1500)
        except Exception:
            return None

    category = safe_text(SELECTORS["category"])
    address = safe_text(SELECTORS["address"])
    phone_btn = safe_attr(SELECTORS["phone"], "data-item-id")
    phone = None
    if phone_btn and phone_btn.startswith("phone:tel:"):
        phone = phone_btn.replace("phone:tel:", "", 1)
    else:
        phone = safe_text(SELECTORS["phone"])

    website = safe_attr(SELECTORS["website"], "href")
    rating = _parse_rating(safe_text(SELECTORS["rating"]))
    reviews_label = None
    try:
        reviews_label = page.locator(SELECTORS["reviews"]).first.get_attribute(
            "aria-label", timeout=1500
        )
    except Exception:
        pass
    review_count = _parse_reviews(reviews_label)
    city = None
    if address and "," in address:
        parts = [p.strip() for p in address.split(",")]
        if len(parts) >= 2:
            city = parts[-2] if len(parts) > 2 else parts[-1]

    return LeadDraft(
        name=name,
        category=category,
        address=address,
        city=city,
        phone=phone,
        website=website,
        gmaps_url=page.url,
        rating=rating,
        review_count=review_count,
        source="gmaps",
    )


def discover(
    niche: str,
    location: str,
    max_leads: int = 20,
    run_id: int | None = None,
    workspace_id: int = 1,
    campaign_id: int | None = None,
    filters: dict[str, Any] | None = None,
) -> int:
    """Search Google Maps and upsert leads. Returns count found."""
    from playwright.sync_api import sync_playwright

    own_run = run_id is None
    if own_run:
        run_id = start_run(workspace_id, "discover_gmaps", campaign_id)

    assert run_id is not None
    found = 0
    errors = 0
    log_buf: list[str] = []
    blocked = False
    max_leads = min(int(max_leads), 150)

    query = f"{niche} in {location}"
    url = f"https://www.google.com/maps/search/{quote_plus(query)}"
    log.info("discover start niche=%s location=%s max=%s", niche, location, max_leads)
    append_run_log(run_id, f"gmaps query: {query}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-dev-shm-usage", "--no-sandbox"],
            )
            context = browser.new_context(
                viewport={"width": 1365, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                ),
                locale="en-US",
            )
            page = context.new_page()
            page.set_default_timeout(20000)
            page.goto(url, wait_until="domcontentloaded")
            _delay(2, 4)

            if page.locator(SELECTORS["unusual"]).count() > 0:
                blocked = True
                log_buf.append("blocked: unusual traffic")
            else:
                seen_hrefs: set[str] = set()
                stagnant = 0
                while found < max_leads and stagnant < 4:
                    links = page.locator(SELECTORS["result_links"])
                    count = links.count()
                    if count == 0:
                        stagnant += 1
                        page.mouse.wheel(0, 2000)
                        _delay(1.5, 3)
                        continue

                    progressed = False
                    for i in range(count):
                        if found >= max_leads:
                            break
                        try:
                            href = links.nth(i).get_attribute("href") or ""
                            if not href or href in seen_hrefs:
                                continue
                            seen_hrefs.add(href)
                            links.nth(i).click(timeout=5000)
                            _delay(2, 5)
                            if page.locator(SELECTORS["unusual"]).count() > 0:
                                blocked = True
                                log_buf.append("blocked mid-run")
                                break
                            draft = _extract_place(page)
                            if not draft:
                                errors += 1
                                continue
                            if not passes_filters(draft, filters):
                                continue
                            upsert_lead(workspace_id, campaign_id, draft)
                            found += 1
                            progressed = True
                            log_buf.append(f"saved: {draft.name}")
                        except Exception as exc:
                            errors += 1
                            log_buf.append(f"error: {exc}")
                            log.exception("place extract failed")

                    if blocked:
                        break
                    if not progressed:
                        stagnant += 1
                    page.mouse.wheel(0, 2500)
                    _delay(1.5, 3.5)

            context.close()
            browser.close()
    except Exception as exc:
        errors += 1
        log_buf.append(f"fatal: {exc}")
        log.exception("gmaps discover failed")
        if own_run:
            finish_run(run_id, "failed", found=found, errors=errors, log="\n".join(log_buf))
        raise

    status = "blocked" if blocked else ("ok" if found else "empty")
    if own_run:
        finish_run(run_id, status, found=found, errors=errors, log="\n".join(log_buf))
    else:
        append_run_log(run_id, "\n".join(log_buf))
        if blocked:
            execute_status = "blocked"
            from common.db import execute

            execute("UPDATE runs SET status = %s WHERE id = %s", (execute_status, run_id))

    log.info("discover done found=%s errors=%s status=%s", found, errors, status)
    return found


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Google Maps discovery CLI")
    parser.add_argument("niche")
    parser.add_argument("location")
    parser.add_argument("max_leads", type=int, nargs="?", default=20)
    parser.add_argument("--workspace-id", type=int, default=1)
    parser.add_argument("--campaign-id", type=int, default=None)
    args = parser.parse_args()
    n = discover(
        args.niche,
        args.location,
        args.max_leads,
        workspace_id=args.workspace_id,
        campaign_id=args.campaign_id,
    )
    print(f"found={n}")


if __name__ == "__main__":
    main()
