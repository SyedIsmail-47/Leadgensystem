"""Static website crawl for emails, socials, tech signals."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from common.logging import get_logger

log = get_logger("scrapers.website")

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
FALSE_EMAIL_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js")

SOCIAL_PATTERNS = {
    "facebook_url": re.compile(r"https?://(www\.)?facebook\.com/[\w.\-/]+", re.I),
    "instagram_url": re.compile(r"https?://(www\.)?instagram\.com/[\w.\-/]+", re.I),
    "linkedin_url": re.compile(r"https?://(www\.)?linkedin\.com/[\w.\-/]+", re.I),
}
WA_RE = re.compile(r"https?://(wa\.me|api\.whatsapp\.com)/[^\s\"'<>]+", re.I)


def _clean_emails(candidates: set[str]) -> list[str]:
    out: list[str] = []
    for e in candidates:
        low = e.lower()
        if any(low.endswith(ext) for ext in FALSE_EMAIL_EXT):
            continue
        if low.endswith((".png", ".jpg")):
            continue
        out.append(e)
    return out


def extract_emails(html: str) -> list[str]:
    found = set(EMAIL_RE.findall(html))
    tree = HTMLParser(html)
    for a in tree.css('a[href^="mailto:"]'):
        href = a.attributes.get("href", "")
        addr = href.replace("mailto:", "").split("?")[0].strip()
        if addr:
            found.add(addr)
    return _clean_emails(found)


def crawl_website(url: str, max_pages: int = 5, timeout: float = 10.0) -> dict[str, Any]:
    """Crawl home + contact/about pages. Fail soft."""
    result: dict[str, Any] = {
        "emails": [],
        "phones": [],
        "facebook_url": None,
        "instagram_url": None,
        "linkedin_url": None,
        "whatsapp_link": None,
        "has_meta_pixel": False,
        "has_google_tag": False,
        "has_booking": False,
        "has_contact_form": False,
        "has_https": url.lower().startswith("https"),
        "has_viewport": False,
        "pages_fetched": 0,
        "error": None,
    }
    if not url:
        result["error"] = "no url"
        return result

    raw = url.strip()
    if not raw.startswith("http"):
        raw = "https://" + raw

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; LeadgensystemBot/1.0; +https://localhost)"
        )
    }
    pages: list[str] = [raw]
    fetched_html: list[str] = []

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            resp = client.get(raw)
            resp.raise_for_status()
            html = resp.text
            fetched_html.append(html)
            result["pages_fetched"] = 1
            result["has_https"] = str(resp.url).startswith("https")

            tree = HTMLParser(html)
            if tree.css_first('meta[name="viewport"]'):
                result["has_viewport"] = True

            # collect contact/about links
            extra: list[str] = []
            for a in tree.css("a[href]"):
                href = a.attributes.get("href") or ""
                text = (a.text() or "").lower()
                low = href.lower()
                if any(k in low or k in text for k in ("contact", "about")):
                    abs_url = urljoin(str(resp.url), href)
                    if urlparse(abs_url).netloc == urlparse(str(resp.url)).netloc:
                        extra.append(abs_url)
            for path in ("/contact", "/about", "/contact-us"):
                extra.append(urljoin(str(resp.url), path))

            seen = {raw.rstrip("/")}
            for link in extra:
                if len(pages) >= max_pages:
                    break
                key = link.rstrip("/")
                if key in seen:
                    continue
                seen.add(key)
                try:
                    r2 = client.get(link)
                    if r2.status_code < 400:
                        fetched_html.append(r2.text)
                        pages.append(link)
                        result["pages_fetched"] += 1
                except Exception:
                    continue
    except Exception as exc:
        result["error"] = str(exc)
        log.warning("crawl failed url=%s err=%s", url, exc)
        return result

    blob = "\n".join(fetched_html)
    emails = extract_emails(blob)
    result["emails"] = emails[:5]

    for field, pattern in SOCIAL_PATTERNS.items():
        m = pattern.search(blob)
        if m:
            result[field] = m.group(0).rstrip(").,")

    wa = WA_RE.search(blob)
    if wa:
        result["whatsapp_link"] = wa.group(0).rstrip(").,")

    low = blob.lower()
    result["has_meta_pixel"] = "fbq(" in low or "connect.facebook.net" in low
    result["has_google_tag"] = "gtag(" in low or "googletagmanager" in low
    result["has_booking"] = any(
        x in low for x in ("calendly.com", "booksy.com", "setmore.com", "simplybook")
    )
    result["has_contact_form"] = "<form" in low and (
        "contact" in low or 'type="email"' in low or "message" in low
    )

    return result
