from __future__ import annotations

import json

import streamlit as st

from common.db import execute, fetchall, fetchone
from dashboard.ui import inject_css, require_login
from scrapers.campaign_discover import discover_campaign, dry_run_query_count
from scoring.rules import DEFAULT_WEIGHTS, evaluate_rules

st.set_page_config(page_title="Campaign Builder", layout="wide")
inject_css()
user = require_login()
ws = user["workspace_id"]

st.title("Campaign Builder")

if "wizard" not in st.session_state:
    st.session_state["wizard"] = {
        "step": 1,
        "name": "",
        "niches": [],
        "locations": [],
        "filters": {
            "min_rating": 0.0,
            "min_reviews": 0,
            "must_website": False,
            "must_phone": False,
            "exclude_keywords": [],
            "max_per_query": 50,
            "max_per_run": 150,
        },
        "sources": {
            "gmaps": True,
            "osm_fallback": True,
            "meta_ads": False,
            "google_ads": False,
            "enrich_depth": 5,
        },
        "weights": dict(DEFAULT_WEIGHTS),
        "scoring_profile_id": None,
        "offer_profile_id": None,
        "sender_profile_id": None,
        "schedule": "once",
        "cron": None,
    }

w = st.session_state["wizard"]
step = w["step"]
st.progress(step / 6, text=f"Step {step} of 6")

# ---- Step 1: Targets ----
if step == 1:
    st.subheader("1 · Targets")
    w["name"] = st.text_input("Campaign name", value=w["name"] or "My campaign")
    niche_in = st.text_input("Add niche / keyword", placeholder="dentist")
    if st.button("Add niche") and niche_in.strip():
        w["niches"] = list(dict.fromkeys([*w["niches"], niche_in.strip()]))
    st.write("Niches:", w["niches"] or "(none)")
    if w["niches"] and st.button("Clear niches"):
        w["niches"] = []

    st.markdown("**Location**")
    c1, c2, c3, c4 = st.columns(4)
    country = c1.text_input("Country", value="PK")
    city = c2.text_input("City", value="Lahore")
    area = c3.text_input("Area / neighborhood", value="")
    radius = c4.number_input("Radius km (optional)", min_value=0.0, value=0.0)
    if st.button("Add location") and city.strip():
        loc = {"country": country, "city": city.strip(), "area": area or None, "radius_km": radius or None}
        w["locations"] = [*w["locations"], loc]
    st.json(w["locations"])

    presets = fetchall(
        "SELECT id, name, value FROM campaign_presets WHERE workspace_id = %s AND kind = 'niche'",
        (ws,),
    )
    if presets:
        p = st.selectbox("Saved niche presets", ["—"] + [p["name"] for p in presets])
        if p != "—" and st.button("Apply niche preset"):
            val = next(x["value"] for x in presets if x["name"] == p)
            if isinstance(val, str):
                val = json.loads(val)
            w["niches"] = list(dict.fromkeys([*w["niches"], *val.get("niches", [])]))

    if st.button("Save current niches as preset") and w["niches"]:
        name = st.session_state.get("preset_name") or w["name"] + " niches"
        execute(
            "INSERT INTO campaign_presets (workspace_id, kind, name, value) VALUES (%s,'niche',%s,%s::jsonb)",
            (ws, name, json.dumps({"niches": w["niches"]})),
        )
        st.success("Preset saved")

    if st.button("Next: Filters", type="primary"):
        if not w["niches"] or not w["locations"]:
            st.error("Add at least one niche and one location")
        else:
            w["step"] = 2
            st.rerun()

# ---- Step 2: Filters ----
elif step == 2:
    st.subheader("2 · Filters")
    f = w["filters"]
    f["min_rating"] = st.slider("Min rating", 0.0, 5.0, float(f.get("min_rating") or 0.0), 0.1)
    f["min_reviews"] = st.number_input("Min reviews", 0, 10000, int(f.get("min_reviews") or 0))
    f["must_website"] = st.checkbox("Must have website", value=bool(f.get("must_website")))
    f["must_phone"] = st.checkbox("Must have phone", value=bool(f.get("must_phone")))
    excl = st.text_input("Exclude keywords (comma-separated)", value=",".join(f.get("exclude_keywords") or []))
    f["exclude_keywords"] = [x.strip() for x in excl.split(",") if x.strip()]
    f["max_per_query"] = st.number_input("Max leads per query", 1, 150, int(f.get("max_per_query") or 50))
    f["max_per_run"] = st.number_input("Max leads per run", 1, 500, int(f.get("max_per_run") or 150))
    b1, b2 = st.columns(2)
    if b1.button("Back"):
        w["step"] = 1
        st.rerun()
    if b2.button("Next: Sources", type="primary"):
        w["step"] = 3
        st.rerun()

# ---- Step 3: Sources ----
elif step == 3:
    st.subheader("3 · Sources")
    s = w["sources"]
    s["gmaps"] = st.checkbox("Google Maps", value=bool(s.get("gmaps", True)))
    s["osm_fallback"] = st.checkbox("OSM fallback", value=bool(s.get("osm_fallback", True)))
    s["meta_ads"] = st.checkbox("Meta Ad Library (stretch)", value=bool(s.get("meta_ads")))
    s["google_ads"] = st.checkbox("Google Ads Transparency (stretch)", value=bool(s.get("google_ads")))
    s["enrich_depth"] = st.slider("Website enrichment max pages", 1, 5, int(s.get("enrich_depth") or 5))
    b1, b2 = st.columns(2)
    if b1.button("Back"):
        w["step"] = 2
        st.rerun()
    if b2.button("Next: Scoring", type="primary"):
        w["step"] = 4
        st.rerun()

# ---- Step 4: Scoring ----
elif step == 4:
    st.subheader("4 · Scoring")
    profiles = fetchall(
        "SELECT id, name, weights FROM scoring_profiles WHERE workspace_id = %s", (ws,)
    )
    names = ["Custom / edit below"] + [p["name"] for p in profiles]
    pick = st.selectbox("Scoring profile", names)
    if pick != "Custom / edit below":
        prof = next(p for p in profiles if p["name"] == pick)
        weights = prof["weights"]
        if isinstance(weights, str):
            weights = json.loads(weights)
        w["weights"] = {**DEFAULT_WEIGHTS, **weights}
        w["scoring_profile_id"] = prof["id"]
    else:
        w["scoring_profile_id"] = None

    cols = st.columns(3)
    for i, (key, val) in enumerate(list(w["weights"].items())):
        w["weights"][key] = cols[i % 3].number_input(key, 0, 30, int(val), key=f"w_{key}")

    sample = fetchone(
        "SELECT * FROM leads WHERE workspace_id = %s ORDER BY id DESC LIMIT 1", (ws,)
    )
    if sample:
        signals = fetchall("SELECT * FROM lead_signals WHERE lead_id = %s", (sample["id"],))
        breakdown = evaluate_rules(sample, signals, niche=w["niches"][0] if w["niches"] else None, weights=w["weights"])
        st.write(f"Live preview on sample lead **{sample['name']}**: {sum(b['points'] for b in breakdown)} pts")
        st.dataframe(breakdown, use_container_width=True, hide_index=True)
    else:
        st.caption("No sample lead yet for live preview.")

    b1, b2 = st.columns(2)
    if b1.button("Back"):
        w["step"] = 3
        st.rerun()
    if b2.button("Next: Offer & Sender", type="primary"):
        w["step"] = 5
        st.rerun()

# ---- Step 5: Offer & Sender ----
elif step == 5:
    st.subheader("5 · Offer & Sender")
    offers = fetchall("SELECT id, name FROM offer_profiles WHERE workspace_id = %s", (ws,))
    senders = fetchall("SELECT id, sender_name, from_email, smtp_verified_at, physical_address FROM sender_profiles WHERE workspace_id = %s", (ws,))
    offer_labels = {f"{o['name']} (#{o['id']})": o["id"] for o in offers}
    if offer_labels:
        okey = st.selectbox("Offer profile", list(offer_labels.keys()))
        w["offer_profile_id"] = offer_labels[okey]
    else:
        st.warning("No offer profiles. Create one in Settings.")
    if senders:
        slabel = {
            f"{s['sender_name']} <{s['from_email']}>"
            + (" ✓" if s.get("smtp_verified_at") and s.get("physical_address") else " (incomplete)"): s["id"]
            for s in senders
        }
        skey = st.selectbox("Sender profile", list(slabel.keys()))
        w["sender_profile_id"] = slabel[skey]
    else:
        st.info("No sender profiles yet. Discovery still works; sending stays disabled until SMTP is verified in Settings.")
        w["sender_profile_id"] = None
    b1, b2 = st.columns(2)
    if b1.button("Back"):
        w["step"] = 4
        st.rerun()
    if b2.button("Next: Schedule & Review", type="primary"):
        w["step"] = 6
        st.rerun()

# ---- Step 6: Schedule & Review ----
elif step == 6:
    st.subheader("6 · Schedule & Review")
    schedule = st.selectbox("Schedule", ["once", "daily", "weekly", "custom"], index=["once", "daily", "weekly", "custom"].index(w.get("schedule") or "once"))
    w["schedule"] = schedule
    cron_map = {"once": None, "daily": "0 9 * * *", "weekly": "0 9 * * 1"}
    if schedule == "custom":
        w["cron"] = st.text_input("Cron", value=w.get("cron") or "0 9 * * *")
    else:
        w["cron"] = cron_map[schedule]

    query_count = len(w["niches"]) * len(w["locations"])
    st.markdown(f"**Dry-run preview:** {query_count} queries ({len(w['niches'])} niches × {len(w['locations'])} locations)")
    st.json({"name": w["name"], "niches": w["niches"], "locations": w["locations"], "filters": w["filters"], "sources": w["sources"], "cron": w["cron"]})

    b1, b2, b3 = st.columns(3)
    if b1.button("Back"):
        w["step"] = 5
        st.rerun()

    def save_campaign() -> int:
        # ensure scoring profile if custom weights
        scoring_id = w.get("scoring_profile_id")
        if scoring_id is None:
            row = fetchone(
                """
                INSERT INTO scoring_profiles (workspace_id, name, weights)
                VALUES (%s, %s, %s::jsonb) RETURNING id
                """,
                (ws, f"{w['name']} weights", json.dumps(w["weights"])),
            )
            scoring_id = row["id"]
        row = fetchone(
            """
            INSERT INTO campaigns (
              workspace_id, name, niche, location, max_leads, schedule_cron, status,
              offer_profile_id, sender_profile_id, scoring_profile_id, filters, sources
            ) VALUES (
              %s,%s,%s,%s,%s,%s,'active',%s,%s,%s,%s::jsonb,%s::jsonb
            ) RETURNING id
            """,
            (
                ws,
                w["name"],
                w["niches"][0],
                f"{w['locations'][0].get('city')}",
                w["filters"].get("max_per_run") or 150,
                w["cron"],
                w.get("offer_profile_id"),
                w.get("sender_profile_id"),
                scoring_id,
                json.dumps(w["filters"]),
                json.dumps(w["sources"]),
            ),
        )
        cid = int(row["id"])
        for n in w["niches"]:
            execute("INSERT INTO campaign_niches (campaign_id, niche) VALUES (%s,%s)", (cid, n))
        for loc in w["locations"]:
            execute(
                """
                INSERT INTO campaign_locations (campaign_id, country, city, area, radius_km)
                VALUES (%s,%s,%s,%s,%s)
                """,
                (cid, loc.get("country"), loc["city"], loc.get("area"), loc.get("radius_km")),
            )
        return cid

    if b2.button("Save campaign", type="primary"):
        cid = save_campaign()
        st.success(f"Saved campaign #{cid} · dry-run queries={dry_run_query_count(cid)}")
        st.session_state["wizard"] = {"step": 1, "name": "", "niches": [], "locations": [], "filters": w["filters"], "sources": w["sources"], "weights": dict(DEFAULT_WEIGHTS), "scoring_profile_id": None, "offer_profile_id": None, "sender_profile_id": None, "schedule": "once", "cron": None}
    if b3.button("Save & Run now"):
        cid = save_campaign()
        with st.spinner("Running discovery…"):
            n = discover_campaign(cid)
        st.success(f"Campaign #{cid} done. Leads touched: {n}")
        st.session_state["wizard"]["step"] = 1
