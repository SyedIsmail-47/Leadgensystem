from __future__ import annotations

import pandas as pd
import streamlit as st

from common.db import execute, fetchall, fetchone
from dashboard.ui import confirm_box, inject_css, require_login
from scoring.engine import score_lead

st.set_page_config(page_title="Leads", layout="wide")
inject_css()
user = require_login()
ws = user["workspace_id"]

st.title("Leads")

campaigns = fetchall(
    "SELECT id, name FROM campaigns WHERE workspace_id = %s ORDER BY name", (ws,)
)
camp_map = {c["name"]: c["id"] for c in campaigns}

f1, f2, f3, f4, f5, f6 = st.columns(6)
camp_name = f1.selectbox("Campaign", ["All"] + list(camp_map.keys()))
tiers = f2.multiselect("Tier", ["A", "B", "C"], default=["A", "B", "C"])
stage = f3.selectbox(
    "Stage",
    ["All", "new", "enriched", "scored", "approved", "contacted", "replied", "won", "lost"],
)
min_score = f4.slider("Min score", 0, 100, 0)
has_email = f5.checkbox("Has email")
search = f6.text_input("Search name")

page = st.number_input("Page", min_value=1, value=1, step=1)
offset = (page - 1) * 50

where = ["workspace_id = %s"]
params: list = [ws]
if camp_name != "All":
    where.append("campaign_id = %s")
    params.append(camp_map[camp_name])
if tiers:
    where.append("tier = ANY(%s)")
    params.append(tiers)
if stage != "All":
    where.append("stage = %s")
    params.append(stage)
where.append("COALESCE(score,0) >= %s")
params.append(min_score)
if has_email:
    where.append("email IS NOT NULL AND email <> ''")
if search:
    where.append("name ILIKE %s")
    params.append(f"%{search}%")

sql = f"""
SELECT id, name, category, city, score, tier, confidence, stage, email, phone, website,
  CASE WHEN gmaps_url IS NOT NULL THEN 'Y' ELSE '' END AS gmaps,
  CASE WHEN website IS NOT NULL THEN 'Y' ELSE '' END AS web,
  CASE WHEN email IS NOT NULL THEN 'Y' ELSE '' END AS em,
  CASE WHEN phone IS NOT NULL THEN 'Y' ELSE '' END AS ph
FROM leads WHERE {' AND '.join(where)}
ORDER BY score DESC NULLS LAST, id DESC
LIMIT 50 OFFSET %s
"""
params.append(offset)
rows = fetchall(sql, tuple(params))
df = pd.DataFrame(rows)
if df.empty:
    st.info("No leads yet. Create a campaign.")
else:
    st.dataframe(df, use_container_width=True, hide_index=True)
    ids = st.multiselect("Select lead IDs", df["id"].tolist())

    b1, b2, b3, b4, b5 = st.columns(5)
    if b1.button("Approve for outreach") and ids:
        execute(
            "UPDATE leads SET stage = 'approved', updated_at = now() WHERE id = ANY(%s) AND workspace_id = %s",
            (ids, ws),
        )
        st.success(f"Approved {len(ids)} leads")
        st.rerun()
    new_stage = b2.selectbox("Change stage to", ["enriched", "scored", "approved", "contacted", "replied", "won", "lost"])
    if b2.button("Apply stage") and ids:
        execute(
            "UPDATE leads SET stage = %s, updated_at = now() WHERE id = ANY(%s) AND workspace_id = %s",
            (new_stage, ids, ws),
        )
        st.success("Stage updated")
        st.rerun()
    if b3.button("Re-score selected") and ids:
        for lid in ids:
            score_lead(int(lid))
        st.success("Re-scored")
        st.rerun()
    if b4.button("Export CSV"):
        st.download_button(
            "Download CSV",
            df.to_csv(index=False).encode("utf-8"),
            file_name="leads.csv",
            mime="text/csv",
        )
    if b5.button("Delete selected") and ids:
        if confirm_box("del_leads"):
            execute("DELETE FROM leads WHERE id = ANY(%s) AND workspace_id = %s", (ids, ws))
            st.success("Deleted")
            st.rerun()

    if st.button("Add selected emails to suppression") and ids:
        for lid in ids:
            row = fetchone("SELECT email FROM leads WHERE id = %s", (lid,))
            if row and row["email"]:
                execute(
                    """
                    INSERT INTO suppression (workspace_id, email, reason)
                    VALUES (%s,%s,'manual') ON CONFLICT DO NOTHING
                    """,
                    (ws, row["email"]),
                )
        st.success("Added to suppression")
