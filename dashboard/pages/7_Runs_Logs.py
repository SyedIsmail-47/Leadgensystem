from __future__ import annotations

import streamlit as st

from common.db import fetchall
from dashboard.ui import inject_css, require_login

st.set_page_config(page_title="Runs & Logs", layout="wide")
inject_css()
user = require_login()
ws = user["workspace_id"]

st.title("Runs & Logs")
rows = fetchall(
    """
    SELECT id, job, campaign_id, status, found, errors, started_at, finished_at
    FROM runs WHERE workspace_id = %s ORDER BY started_at DESC LIMIT 100
    """,
    (ws,),
)
blocked = [r for r in rows if r["status"] == "blocked"]
if blocked:
    st.error(
        f"{len(blocked)} blocked run(s). Wait, lower volume, or enable OSM fallback."
    )
st.dataframe(rows, use_container_width=True, hide_index=True)
if rows:
    pick = st.selectbox("View log", [r["id"] for r in rows])
    from common.db import fetchone

    full = fetchone("SELECT log FROM runs WHERE id = %s", (pick,))
    st.code(full["log"] or "(empty)")
