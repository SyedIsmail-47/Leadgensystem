"""Static website crawl for emails, socials, tech signals."""
from __future__ import annotations

import re
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

import httpx
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from common.logging import get_logger

log = get_logger("scrapers.website")

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
OBFUSCATED_EMAIL_RE = re.compile(
    r"([a-zA-Z0-9._%+\-]+)\s*(?:\[at\]|\(at\)|\sat\s)\s*([a-zA-Z0-9.\-]+)\s*(?:\[dot\]|\(dot\)|\sdot\s)\s*([a-zA-Z]{2,})",
    re.I,
)
FALSE_EMAIL_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js")
IGNORED_EMAILS = {"example@example.com", "email@example.com", "name@example.com"}

SHARE_FRAGMENTS = ("/sharer", "/share", "share.php", "intent/tweet")


def _clean_emails(candidates: set[str]) -> list[str]:
    out: list[str] = []
    for e in candidates:
        low = e.lower().strip()
        if any(low.endswith(ext) for ext in FALSE_EMAIL_EXT):
            continue
        if "@" in low and any(low.split("@", 1)[0].endswith(x) for x in ("2x", "3x")):
            # logo@2x.png style already caught by ext; keep defensive
            continue
        if low in IGNORED_EMAILS:
            continue
        if re.search(r"@\d+x\.", low):
            continue
        out.append(e.strip())
    return out


def extract_emails(html: str) -> list[str]:
    found: set[str] = set(EMAIL_RE.findall(html))
    for m in OBFUSCATED_EMAIL_RE.finditer(html):
        found.add(f"{m.group(1)}@{m.group(2)}.{m.group(3)}".lower())
    tree = HTMLParser(html)
    for a in tree.css('a[href^="mailto:"]'):
        href = a.attributes.get("href", "")
        addr = href.replace("mailto:", "").split("?")[0].strip()
        if addr:
            found.add(addr)
    return _clean_emails(found)


def _is_share_url(url: str) -> bool:
    low = url.lower()
    return any(frag in low for frag in SHARE_FRAGMENTS)


def _first_social(blob: str, pattern: re.Pattern[str]) -> str | None:
    for m in pattern.finditer(blob):
        url = m.group(0).rstrip(").,")
        if not _is_share_url(url):
            return url
    return None


def analyze_html(html: str, *, base_url: str = "https://example.com") -> dict[str, Any]:
    """Extract enrichment signals from HTML (no network)."""
    result: dict[str, Any] = {
        "emails": extract_emails(html),
        "phones": [],
        "facebook_url": _first_social(
            html, re.compile(r"https?://(www\.)?facebook\.com/[\w.\-/]+", re.I)
        ),
        "instagram_url": _first_social(
            html, re.compile(r"https?://(www\.)?instagram\.com/[\w.\-/]+", re.I)
        ),
        "linkedin_url": _first_social(
            html, re.compile(r"https?://(www\.)?linkedin\.com/[\w.\-/]+", re.I)
        ),
        "whatsapp_link": None,
        "has_meta_pixel": False,
        "has_google_tag": False,
        "has_booking": False,
        "has_contact_form": False,
        "has_https": base_url.lower().startswith("https"),
        "has_viewport": False,
        "pages_fetched": 1,
        "error": None,
        "same_domain_links": [],
    }
    wa = re.search(r"https?://(wa\.me|api\.whatsapp\.com)/[^\s\"'<>]+", html, re.I)
    if wa:
        result["whatsapp_link"] = wa.group(0).rstrip(").,")

    tree = HTMLParser(html)
    if tree.css_first('meta[name="viewport"]'):
        result["has_viewport"] = True

    low = html.lower()
    result["has_meta_pixel"] = "fbq(" in low or "connect.facebook.net" in low
    result["has_google_tag"] = "gtag(" in low or "googletagmanager.com" in low
    result["has_booking"] = any(
        x in low for x in ("calendly.com", "booksy.com", "setmore.com", "simplybook")
    )
    result["has_contact_form"] = "<form" in low and (
        "contact" in low or 'type="email"' in low or "message" in low
    )

    base_host = urlparse(base_url).netloc
    for a in tree.css("a[href]"):
        href = a.attributes.get("href") or ""
        abs_url = urljoin(base_url, href)
        if urlparse(abs_url).netloc == base_host:
            result["same_domain_links"].append(abs_url)
    return result


Fetcher = Callable[[str], tuple[int, str]]


def crawl_website(
    url: str,
    max_pages: int = 5,
    timeout: float = 10.0,
    fetcher: Fetcher | None = None,
) -> dict[str, Any]:
    """Crawl home + contact/about pages. Fail soft. Max 5 same-domain pages."""
    empty: dict[str, Any] = {
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
        "has_https": False,
        "has_viewport": False,
        "pages_fetched": 0,
        "error": None,
        "same_domain_links": [],
    }
    if not url:
        empty["error"] = "no url"
        return empty

    raw = url.strip()
    if not raw.startswith("http"):
        raw = "https://" + raw

    pages_html: list[str] = []
    fetched_urls: list[str] = []

    def default_fetch(u: str) -> tuple[int, str]:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; LeadgensystemBot/1.0; +https://localhost)"
        }
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            resp = client.get(u)
            return resp.status_code, resp.text

    fetch = fetcher or default_fetch

    try:
        status, html = fetch(raw)
        if status >= 500:
            empty["error"] = f"http {status}"
            return empty
        if status >= 400:
            empty["error"] = f"http {status}"
            return empty
        pages_html.append(html)
        fetched_urls.append(raw)
        analyzed0 = analyze_html(html, base_url=raw)

        extras: list[str] = []
        for link in analyzed0.get("same_domain_links") or []:
            low = link.lower()
            if any(k in low for k in ("contact", "about")):
                extras.append(link)
        for path in ("/contact", "/about", "/contact-us"):
            extras.append(urljoin(raw, path))

        seen = {raw.rstrip("/")}
        for link in extras:
            if len(fetched_urls) >= max_pages:
                break
            key = link.rstrip("/")
            if key in seen:
                continue
            if urlparse(link).netloc != urlparse(raw).netloc:
                continue
            seen.add(key)
            try:
                st, body = fetch(link)
                if st < 400:
                    pages_html.append(body)
                    fetched_urls.append(link)
            except Exception:
                continue
    except Exception as exc:
        empty["error"] = str(exc)
        log.warning("crawl failed url=%s err=%s", url, exc)
        return empty

    blob = "\n".join(pages_html)
    result = analyze_html(blob, base_url=raw)
    result["pages_fetched"] = len(fetched_urls)
    result["fetched_urls"] = fetched_urls
    result["has_https"] = raw.startswith("https")
    return result
