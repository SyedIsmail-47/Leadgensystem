"""URL normalization helpers."""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "mc_cid",
    "mc_eid",
}


def normalize_url(url: str | None) -> str | None:
    """Add scheme if missing; strip tracking params and fragments."""
    if not url or not str(url).strip():
        return None
    raw = str(url).strip()
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    parsed = urlparse(raw)
    query = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS
    ]
    cleaned = parsed._replace(query=urlencode(query), fragment="")
    return urlunparse(cleaned)
