from __future__ import annotations

import streamlit as st

from common.db import execute, fetchall, fetchone
from dashboard.ui import inject_css, require_login
from outreach.sender import can_send, send_step
from outreach.sequences import approve_steps, approve_tier_a, enqueue_sequence

st.set_page_config(page_title="Outreach", layout="wide")
inject_css()
user = require_login()
ws = user["workspace_id"]

st.title("Outreach")

sender_ok = fetchone(
    """
    SELECT id, sender_name, physical_address, smtp_verified_at
    FROM sender_profiles
    WHERE workspace_id = %s
    ORDER BY smtp_verified_at NULLS LAST, id
    LIMIT 1
    """,
    (ws,),
)
if not can_send(sender_ok):
    st.warning(
        "Email sending is disabled until a Sender Profile has a physical address and a passing SMTP test (Settings)."
    )
else:
    st.success(f"Sender ready: {sender_ok['sender_name']}")

sent_today = fetchone(
    """
    SELECT COUNT(*) AS c FROM outreach_steps
    WHERE workspace_id = %s AND status='sent' AND sent_at::date = CURRENT_DATE
    """,
    (ws,),
)
limit = (sender_ok or {}).get("daily_limit") if sender_ok else 20
st.caption(f"Sent today: {sent_today['c'] if sent_today else 0} / {limit or 20}")

st.subheader("Enqueue sequences")
approved_leads = fetchall(
    """
    SELECT id, name, email, tier FROM leads
    WHERE workspace_id = %s AND email IS NOT NULL AND stage IN ('approved','scored')
    ORDER BY score DESC NULLS LAST LIMIT 100
    """,
    (ws,),
)
if approved_leads:
    pick = st.multiselect(
        "Leads to enqueue",
        options=[r["id"] for r in approved_leads],
        format_func=lambda i: next(f"{x['name']} <{x['email']}> [{x.get('tier')}]" for x in approved_leads if x["id"] == i),
    )
    if st.button("Create 3-step sequences"):
        n = 0
        for lid in pick:
            n += enqueue_sequence(int(lid))
        st.success(f"Created {n} steps")
        st.rerun()
else:
    st.info("Approve scored leads (with email) first, then enqueue here.")

pending, scheduled, sent, suppressed = st.tabs(
    ["Pending approval", "Scheduled", "Sent", "Suppressed"]
)

with pending:
    rows = fetchall(
        """
        SELECT os.id, os.step, os.subject, os.body, os.scheduled_for, l.name, l.email, l.tier
        FROM outreach_steps os JOIN leads l ON l.id = os.lead_id
        WHERE os.workspace_id = %s AND os.status = 'pending'
        ORDER BY os.id DESC LIMIT 100
        """,
        (ws,),
    )
    if not rows:
        st.write("No pending steps.")
    else:
        for r in rows:
            with st.expander(f"#{r['id']} step {r['step']} · {r['name']} · {r['subject']}"):
                st.write(r["body"])
                edited = st.text_area("Edit body", value=r["body"] or "", key=f"body_{r['id']}")
                if st.button("Save edit", key=f"save_{r['id']}"):
                    execute("UPDATE outreach_steps SET body=%s WHERE id=%s", (edited, r["id"]))
                    st.success("Saved")
                if st.button("Approve", key=f"ap_{r['id']}"):
                    approve_steps([int(r["id"])])
                    st.rerun()
        if st.button("Approve all Tier A"):
            n = approve_tier_a(ws)
            st.success(f"Approved {n}")
            st.rerun()

with scheduled:
    rows = fetchall(
        """
        SELECT os.id, os.step, os.subject, os.scheduled_for, l.name, l.email
        FROM outreach_steps os JOIN leads l ON l.id = os.lead_id
        WHERE os.workspace_id = %s AND os.status = 'approved'
        ORDER BY os.scheduled_for NULLS FIRST LIMIT 100
        """,
        (ws,),
    )
    st.dataframe(rows, use_container_width=True, hide_index=True)
    ids = st.multiselect("Send now (bypass schedule)", [r["id"] for r in rows] if rows else [])
    if st.button("Send selected now") and ids:
        if not can_send(sender_ok):
            st.error("Sender not ready")
        else:
            ok = 0
            for sid in ids:
                if send_step(int(sid)):
                    ok += 1
            st.success(f"Sent {ok}")
            st.rerun()

with sent:
    rows = fetchall(
        """
        SELECT os.id, os.step, os.subject, os.sent_at, l.name, l.email, os.error
        FROM outreach_steps os JOIN leads l ON l.id = os.lead_id
        WHERE os.workspace_id = %s AND os.status IN ('sent','failed','skipped')
        ORDER BY COALESCE(os.sent_at, os.scheduled_for) DESC NULLS LAST LIMIT 100
        """,
        (ws,),
    )
    st.dataframe(rows, use_container_width=True, hide_index=True)

with suppressed:
    rows = fetchall(
        "SELECT email, reason, added_at FROM suppression WHERE workspace_id = %s ORDER BY added_at DESC",
        (ws,),
    )
    st.dataframe(rows, use_container_width=True, hide_index=True)
    email = st.text_input("Add email to suppression")
    if st.button("Add") and email:
        execute(
            """
            INSERT INTO suppression (workspace_id, email, reason) VALUES (%s,%s,'manual')
            ON CONFLICT DO NOTHING
            """,
            (ws, email.lower().strip()),
        )
        st.rerun()
