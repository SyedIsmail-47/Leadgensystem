from __future__ import annotations

import streamlit as st

from common.db import execute, fetchall, fetchone
from dashboard.ui import inject_css, require_login, score_bar, stage_chip, tier_chip

st.set_page_config(page_title="Lead Detail", layout="wide")
inject_css()
user = require_login()
ws = user["workspace_id"]

st.title("Lead Detail")
leads = fetchall(
    "SELECT id, name FROM leads WHERE workspace_id = %s ORDER BY score DESC NULLS LAST LIMIT 500",
    (ws,),
)
if not leads:
    st.info("No leads yet. Create a campaign.")
    st.stop()

options = {f"{r['id']} — {r['name']}": r["id"] for r in leads}
choice = st.selectbox("Lead", list(options.keys()))
lead_id = options[choice]
lead = fetchone("SELECT * FROM leads WHERE id = %s AND workspace_id = %s", (lead_id, ws))
assert lead

h1, h2, h3 = st.columns([3, 1, 2])
h1.markdown(f"## {lead['name']}")
h2.markdown(tier_chip(lead.get("tier")) + " " + stage_chip(lead.get("stage")), unsafe_allow_html=True)
h3.markdown(score_bar(lead.get("score")), unsafe_allow_html=True)

stages = ["new", "enriched", "scored", "approved", "contacted", "replied", "won", "lost"]
new_stage = st.selectbox("Stage", stages, index=stages.index(lead["stage"]) if lead["stage"] in stages else 0)
if st.button("Update stage"):
    execute("UPDATE leads SET stage = %s, updated_at = now() WHERE id = %s", (new_stage, lead_id))
    st.success("Updated")
    st.rerun()

left, mid, right = st.columns(3)
with left:
    st.subheader("Contact")
    st.write(f"Phone: {lead.get('phone') or '—'}")
    st.write(f"Email: {lead.get('email') or '—'}")
    st.write(f"Website: {lead.get('website') or '—'}")
    st.write(f"City: {lead.get('city') or '—'}")
    st.write(f"Rating: {lead.get('rating') or '—'} ({lead.get('review_count') or 0} reviews)")
    if lead.get("gmaps_url"):
        st.markdown(f"[Google Maps]({lead['gmaps_url']})")
    if lead.get("whatsapp_link"):
        st.markdown(f"[WhatsApp]({lead['whatsapp_link']})")
    elif lead.get("phone"):
        digits = "".join(c for c in str(lead["phone"]) if c.isdigit())
        st.markdown(f"[WhatsApp chat](https://wa.me/{digits})")
    for label, key in [("Facebook", "facebook_url"), ("Instagram", "instagram_url"), ("LinkedIn", "linkedin_url")]:
        if lead.get(key):
            st.markdown(f"[{label}]({lead[key]})")

with mid:
    st.subheader("Score breakdown")
    scores = fetchall(
        "SELECT rule, points, detail FROM lead_scores WHERE lead_id = %s ORDER BY id",
        (lead_id,),
    )
    st.dataframe(scores, use_container_width=True, hide_index=True)
    st.metric("Confidence", f"{float(lead.get('confidence') or 0):.0%}")

with right:
    st.subheader("Signals")
    signals = fetchall(
        "SELECT channel, signal, value, verified, observed_at FROM lead_signals WHERE lead_id = %s ORDER BY observed_at DESC",
        (lead_id,),
    )
    st.dataframe(signals, use_container_width=True, hide_index=True)
    st.subheader("Notes")
    notes = st.text_area("Notes", value=lead.get("notes") or "", height=120)
    if st.button("Save notes"):
        execute("UPDATE leads SET notes = %s, updated_at = now() WHERE id = %s", (notes, lead_id))
        st.success("Saved")
    c1, c2 = st.columns(2)
    if c1.button("Mark replied"):
        execute("UPDATE leads SET stage = 'replied', updated_at = now() WHERE id = %s", (lead_id,))
        st.rerun()
    outcome = c2.selectbox("Outcome", ["won", "lost"])
    if c2.button("Mark outcome"):
        execute("UPDATE leads SET stage = %s, updated_at = now() WHERE id = %s", (outcome, lead_id))
        st.rerun()
