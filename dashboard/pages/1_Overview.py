from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from common.db import fetchall, fetchone
from dashboard.ui import inject_css, require_login

st.set_page_config(page_title="Overview", layout="wide")
inject_css()
user = require_login()
ws = user["workspace_id"]

st.title("Overview")

kpis = fetchone(
    """
    SELECT
      COUNT(*) AS total,
      COUNT(*) FILTER (WHERE tier = 'A') AS tier_a,
      COUNT(*) FILTER (WHERE stage IN ('contacted','replied','won')
        AND updated_at >= now() - interval '7 days') AS contacted_week,
      COUNT(*) FILTER (WHERE stage = 'replied') AS replied,
      COUNT(*) FILTER (WHERE stage = 'contacted') AS contacted
    FROM leads WHERE workspace_id = %s
    """,
    (ws,),
)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total leads", int(kpis["total"] or 0))
c2.metric("Tier A leads", int(kpis["tier_a"] or 0))
c3.metric("Contacted this week", int(kpis["contacted_week"] or 0))
reply_rate = 0.0
if kpis["contacted"]:
    reply_rate = round(100.0 * float(kpis["replied"] or 0) / float(kpis["contacted"]), 1)
c4.metric("Reply rate", f"{reply_rate}%")

funnel_stages = ["new", "enriched", "scored", "approved", "contacted", "replied", "won"]
funnel_rows = []
for stage in funnel_stages:
    row = fetchone(
        "SELECT COUNT(*) AS c FROM leads WHERE workspace_id = %s AND stage = %s",
        (ws, stage),
    )
    funnel_rows.append({"stage": stage, "count": int(row["c"] or 0)})
fig = px.bar(pd.DataFrame(funnel_rows), x="stage", y="count", title="Pipeline funnel")
st.plotly_chart(fig, use_container_width=True)

col_a, col_b = st.columns(2)
with col_a:
    by_tier = fetchall(
        """
        SELECT COALESCE(c.name,'(none)') AS campaign, COALESCE(l.tier,'C') AS tier, COUNT(*) AS n
        FROM leads l LEFT JOIN campaigns c ON c.id = l.campaign_id
        WHERE l.workspace_id = %s
        GROUP BY 1,2 ORDER BY 1,2
        """,
        (ws,),
    )
    if by_tier:
        st.plotly_chart(
            px.bar(pd.DataFrame(by_tier), x="campaign", y="n", color="tier", barmode="stack",
                   title="Leads per campaign by tier"),
            use_container_width=True,
        )
    else:
        st.info("No leads yet. Create a campaign.")

with col_b:
    daily = fetchall(
        """
        SELECT date_trunc('day', created_at)::date AS day, COUNT(*) AS n
        FROM leads WHERE workspace_id = %s AND created_at >= now() - interval '30 days'
        GROUP BY 1 ORDER BY 1
        """,
        (ws,),
    )
    if daily:
        st.plotly_chart(
            px.line(pd.DataFrame(daily), x="day", y="n", title="Leads added (30 days)"),
            use_container_width=True,
        )

st.subheader("Needs attention")
blocked = fetchall(
    """
    SELECT id, job, status, started_at FROM runs
    WHERE workspace_id = %s AND status = 'blocked'
    ORDER BY started_at DESC LIMIT 10
    """,
    (ws,),
)
pending = fetchone(
    """
    SELECT COUNT(*) AS c FROM outreach_steps
    WHERE workspace_id = %s AND status = 'pending'
    """,
    (ws,),
)
if blocked:
    st.warning(f"{len(blocked)} blocked scraper run(s). Consider OSM fallback or lower volume.")
    st.dataframe(pd.DataFrame(blocked), use_container_width=True)
if pending and pending["c"]:
    st.info(f"{pending['c']} outreach steps pending approval.")
if not blocked and not (pending and pending["c"]):
    st.success("Nothing urgent.")
