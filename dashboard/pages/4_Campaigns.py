from __future__ import annotations

import streamlit as st

from common.db import execute, fetchall, fetchone
from dashboard.ui import confirm_box, inject_css, require_login
from scrapers.campaign_discover import discover_campaign, dry_run_query_count

st.set_page_config(page_title="Campaigns", layout="wide")
inject_css()
user = require_login()
ws = user["workspace_id"]

st.title("Campaigns")
st.caption("Create campaigns in Campaign Builder. Manage runs here.")

rows = fetchall(
    """
    SELECT c.*,
      (SELECT COUNT(*) FROM leads l WHERE l.campaign_id = c.id) AS lead_count,
      (SELECT status FROM runs r WHERE r.campaign_id = c.id ORDER BY r.started_at DESC LIMIT 1) AS last_status
    FROM campaigns c
    WHERE c.workspace_id = %s
    ORDER BY c.created_at DESC
    """,
    (ws,),
)

if not rows:
    st.info("No campaigns yet. Open Campaign Builder.")
else:
    for c in rows:
        with st.container(border=True):
            cols = st.columns([3, 1, 1, 1, 1])
            cols[0].markdown(f"**{c['name']}** · status `{c['status']}` · leads `{c['lead_count']}`")
            cols[1].write(f"Last: {c.get('last_status') or '—'}")
            qn = dry_run_query_count(int(c["id"]))
            cols[2].write(f"Queries: {qn}")
            if cols[3].button("Run now", key=f"run_{c['id']}"):
                with st.spinner("Discovering…"):
                    n = discover_campaign(int(c["id"]))
                st.success(f"Found/upserted {n} leads")
                st.rerun()
            if cols[4].button("Pause" if c["status"] == "active" else "Resume", key=f"pause_{c['id']}"):
                new_status = "paused" if c["status"] == "active" else "active"
                execute("UPDATE campaigns SET status = %s WHERE id = %s", (new_status, c["id"]))
                st.rerun()
            if st.button("Delete", key=f"del_{c['id']}"):
                if confirm_box(f"confirm_del_{c['id']}"):
                    execute("DELETE FROM campaigns WHERE id = %s AND workspace_id = %s", (c["id"], ws))
                    st.success("Deleted")
                    st.rerun()
