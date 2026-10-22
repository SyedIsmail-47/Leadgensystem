"""Default scoring weights and pure rule evaluators."""
from __future__ import annotations

from typing import Any

DEFAULT_WEIGHTS: dict[str, int] = {
    "has_website": 8,
    "category_match": 8,
    "rating_ge_4": 6,
    "reviews_ge_20": 6,
    "inside_location": 6,
    "opportunity_gap": 6,
    "meta_ads": 15,
    "google_ads": 10,
    "has_pixel_or_tag": 5,
    "email_mx_valid": 12,
    "valid_phone": 8,
    "whatsapp_link": 5,
    "active_social": 5,
}


def evaluate_rules(
    lead: dict[str, Any],
    signals: list[dict[str, Any]],
    *,
    niche: str | None = None,
    location: str | None = None,
    weights: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    sig_set = {(s["channel"], s["signal"]) for s in signals}
    sig_verified = {
        (s["channel"], s["signal"]) for s in signals if s.get("verified")
    }
    breakdown: list[dict[str, Any]] = []

    def add(rule: str, ok: bool, detail: str) -> None:
        pts = int(w.get(rule, 0)) if ok else 0
        breakdown.append({"rule": rule, "points": pts, "detail": detail})

    add("has_website", bool(lead.get("website")), "has website" if lead.get("website") else "no website")

    cat = (lead.get("category") or "").lower()
    niche_l = (niche or "").lower()
    cat_ok = bool(niche_l) and (niche_l in cat or cat in niche_l or niche_l in (lead.get("name") or "").lower())
    # if no niche provided, grant when category present
    if not niche_l:
        cat_ok = bool(cat)
    add("category_match", cat_ok, f"category={lead.get('category')}")

    rating = lead.get("rating")
    add("rating_ge_4", rating is not None and float(rating) >= 4.0, f"rating={rating}")

    reviews = lead.get("review_count") or 0
    add("reviews_ge_20", int(reviews) >= 20, f"reviews={reviews}")

    loc_ok = False
    if location:
        loc_l = location.lower()
        hay = " ".join(
            str(x) for x in [lead.get("city"), lead.get("address")] if x
        ).lower()
        loc_ok = any(part.strip() in hay for part in loc_l.split(",") if part.strip())
    add("inside_location", loc_ok, f"city={lead.get('city')}")

    gap = (
        ("website", "no_pixel") in sig_set
        or ("website", "no_booking") in sig_set
        or ("website", "no_contact_form") in sig_set
    )
    add("opportunity_gap", gap, "gap signals present" if gap else "no gap")

    add("meta_ads", ("ads", "meta_ads") in sig_verified or ("meta_ads", "running_ads") in sig_verified, "meta ads")
    add(
        "google_ads",
        ("ads", "google_ads") in sig_verified or ("google_ads", "running_ads") in sig_verified,
        "google ads",
    )
    pixel = ("website", "has_pixel") in sig_set or ("website", "has_google_tag") in sig_set
    add("has_pixel_or_tag", pixel, "pixel/tag")

    email_ok = ("email", "email_found") in sig_verified or (
        bool(lead.get("email")) and any(
            s["channel"] == "email" and s.get("verified") for s in signals
        )
    )
    add("email_mx_valid", email_ok or bool(lead.get("email")), f"email={lead.get('email')}")

    phone_ok = ("phone", "valid_phone") in sig_verified or bool(lead.get("phone"))
    add("valid_phone", phone_ok, f"phone={lead.get('phone')}")

    wa = bool(lead.get("whatsapp_link")) or ("phone", "whatsapp_link") in sig_set
    add("whatsapp_link", wa, "whatsapp")

    social = any(
        [
            lead.get("facebook_url"),
            lead.get("instagram_url"),
            lead.get("linkedin_url"),
            ("social", "facebook_url") in sig_set,
            ("social", "instagram_url") in sig_set,
            ("social", "linkedin_url") in sig_set,
        ]
    )
    add("active_social", social, "social profile")

    return breakdown


def compute_confidence(signals: list[dict[str, Any]]) -> float:
    """Independent channels with >=1 verified signal / 5."""
    channels = set()
    for s in signals:
        if not s.get("verified"):
            continue
        ch = s["channel"]
        if ch in ("email", "phone"):
            channels.add("email_phone")
        elif ch in ("meta_ads", "google_ads", "ads"):
            channels.add("ads")
        elif ch in ("gmaps", "website", "social"):
            channels.add(ch)
    # also map
    mapped = set()
    for ch in channels:
        if ch == "email_phone":
            mapped.add("email_phone")
        else:
            mapped.add(ch)
    # normalize to 5 buckets: gmaps, website, social, ads, email/phone
    buckets = set()
    for s in signals:
        if not s.get("verified"):
            continue
        ch = s["channel"]
        if ch == "gmaps":
            buckets.add("gmaps")
        elif ch == "website":
            buckets.add("website")
        elif ch == "social":
            buckets.add("social")
        elif ch in ("ads", "meta_ads", "google_ads"):
            buckets.add("ads")
        elif ch in ("email", "phone"):
            buckets.add("email_phone")
    return round(len(buckets) / 5.0, 2)


def tier_for(score: int, has_reachable: bool) -> str:
    if score >= 70:
        t = "A"
    elif score >= 45:
        t = "B"
    else:
        t = "C"
    if not has_reachable and t != "C":
        return "C"
    return t
