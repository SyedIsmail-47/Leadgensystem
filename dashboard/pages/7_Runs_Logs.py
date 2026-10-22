from __future__ import annotations

import streamlit as st

from common.db import fetchall, fetchone
from dashboard.ui import inject_css, require_login

st.set_page_config(page_title="Runs & Logs", layout="wide")
inject_css()
user = require_login()
ws = user["workspace_id"]

st.title("Runs & Logs")

blocked = fetchall(
    """
    SELECT id, job, campaign_id, started_at, log
    FROM runs WHERE workspace_id = %s AND status = 'blocked'
    ORDER BY started_at DESC LIMIT 20
    """,
    (ws,),
)
if blocked:
    st.error(
        f"{len(blocked)} blocked scraper run(s). Suggested actions: wait, lower "
        "`max_per_query` / `max_per_run`, enable OSM fallback in Campaign Builder."
    )

rows = fetchall(
    """
    SELECT id, job, campaign_id, status, found, errors,
           started_at, finished_at,
           EXTRACT(EPOCH FROM (COALESCE(finished_at, now()) - started_at))::int AS duration_s
    FROM runs WHERE workspace_id = %s
    ORDER BY started_at DESC LIMIT 100
    """,
    (ws,),
)
st.dataframe(rows, use_container_width=True, hide_index=True)

if rows:
    pick = st.selectbox("Expand log", [r["id"] for r in rows])
    full = fetchone("SELECT job, status, log FROM runs WHERE id = %s", (pick,))
    st.subheader(f"Run #{pick} · {full['job']} · {full['status']}")
    st.code(full["log"] or "(empty)")
else:
    st.info("No runs yet. Use Campaigns → Run now.")
