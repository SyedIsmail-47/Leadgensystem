from __future__ import annotations

import json
import smtplib
from email.message import EmailMessage
from datetime import datetime, timezone

import streamlit as st

from common.auth import hash_password, verify_password
from common.db import execute, fetchall, fetchone
from dashboard.ui import confirm_box, inject_css, require_login
from scoring.rules import DEFAULT_WEIGHTS

st.set_page_config(page_title="Settings", layout="wide")
inject_css()
user = require_login()
ws = user["workspace_id"]

st.title("Settings")
tab_offer, tab_sender, tab_scoring, tab_account = st.tabs(
    ["Offer Profiles", "Sender Profiles", "Scoring Profiles", "Account"]
)

with tab_offer:
    st.subheader("Offer Profiles")
    offers = fetchall("SELECT * FROM offer_profiles WHERE workspace_id = %s ORDER BY id", (ws,))
    for o in offers:
        with st.expander(f"{o['name']} (#{o['id']})"):
            name = st.text_input("Name", value=o["name"], key=f"on_{o['id']}")
            pitch = st.text_area("Pitch", value=o.get("pitch") or "", key=f"op_{o['id']}")
            pains = st.text_input(
                "Pain points (comma-separated)",
                value=", ".join(o.get("pain_points") or []),
                key=f"opp_{o['id']}",
            )
            hooks = st.text_area(
                "Gap hook rules (JSON)",
                value=json.dumps(o.get("gap_hook_rules") or [], indent=2),
                key=f"oh_{o['id']}",
            )
            templates = st.text_area(
                "Templates JSON (step1/2/3 subject+body)",
                value=json.dumps(o.get("templates") or {}, indent=2),
                key=f"ot_{o['id']}",
            )
            sample_body = ""
            try:
                t = json.loads(templates) if isinstance(templates, str) else templates
                sample_body = (t.get("step1") or {}).get("body", "")
                sample_body = (
                    sample_body.replace("{{name}}", "Acme Dental")
                    .replace("{{category}}", "Dentist")
                    .replace("{{city}}", "Lahore")
                    .replace("{{gap_hook}}", "noticed you run no tracking on your site")
                    .replace("{{sender_name}}", "You")
                )
            except Exception:
                pass
            if sample_body:
                st.markdown("**Live preview (step 1)**")
                st.code(sample_body)
            c1, c2 = st.columns(2)
            if c1.button("Save", key=f"os_{o['id']}"):
                execute(
                    """
                    UPDATE offer_profiles SET name=%s, pitch=%s, pain_points=%s,
                      gap_hook_rules=%s::jsonb, templates=%s::jsonb
                    WHERE id=%s AND workspace_id=%s
                    """,
                    (
                        name,
                        pitch,
                        [x.strip() for x in pains.split(",") if x.strip()],
                        hooks,
                        templates,
                        o["id"],
                        ws,
                    ),
                )
                st.success("Saved")
            if c2.button("Delete", key=f"od_{o['id']}") and confirm_box(f"odel_{o['id']}"):
                execute("DELETE FROM offer_profiles WHERE id=%s AND workspace_id=%s", (o["id"], ws))
                st.rerun()

    st.markdown("---")
    st.subheader("New offer profile")
    with st.form("new_offer"):
        n_name = st.text_input("Name")
        n_pitch = st.text_input("Pitch")
        if st.form_submit_button("Create"):
            execute(
                """
                INSERT INTO offer_profiles (workspace_id, name, pitch, gap_hook_rules, templates)
                VALUES (%s,%s,%s,'[]'::jsonb,'{}'::jsonb)
                """,
                (ws, n_name, n_pitch),
            )
            st.success("Created")
            st.rerun()

with tab_sender:
    st.subheader("Sender Profiles")
    st.caption("Sending stays disabled until physical address is set and SMTP test passes.")
    senders = fetchall("SELECT * FROM sender_profiles WHERE workspace_id = %s ORDER BY id", (ws,))
    for s in senders:
        with st.expander(f"{s['sender_name']} <{s['from_email']}>"):
            sn = st.text_input("Sender name", value=s["sender_name"], key=f"sn_{s['id']}")
            company = st.text_input("Company", value=s.get("company") or "", key=f"sc_{s['id']}")
            from_email = st.text_input("From email", value=s["from_email"], key=f"sf_{s['id']}")
            reply_to = st.text_input("Reply-to", value=s.get("reply_to") or "", key=f"sr_{s['id']}")
            domain = st.text_input("Domain", value=s.get("domain") or "", key=f"sd_{s['id']}")
            addr = st.text_area("Physical address", value=s.get("physical_address") or "", key=f"sa_{s['id']}")
            smtp_host = st.text_input("SMTP host", value=s.get("smtp_host") or "", key=f"sh_{s['id']}")
            smtp_port = st.number_input("SMTP port", 1, 65535, int(s.get("smtp_port") or 587), key=f"sp_{s['id']}")
            smtp_user = st.text_input("SMTP user", value=s.get("smtp_user") or "", key=f"su_{s['id']}")
            smtp_pass = st.text_input("SMTP password", type="password", key=f"sw_{s['id']}")
            daily = st.number_input("Daily limit", 1, 500, int(s.get("daily_limit") or 20), key=f"sl_{s['id']}")
            wstart = st.number_input("Send window start hour", 0, 23, int(s.get("send_window_start") or 9), key=f"ss_{s['id']}")
            wend = st.number_input("Send window end hour", 0, 23, int(s.get("send_window_end") or 17), key=f"se_{s['id']}")
            tz = st.text_input("Timezone", value=s.get("timezone") or "UTC", key=f"st_{s['id']}")
            st.write("Verified at:", s.get("smtp_verified_at") or "never")
            if st.button("Save sender", key=f"ssave_{s['id']}"):
                pass_enc = s.get("smtp_pass_enc")
                if smtp_pass:
                    pass_enc = smtp_pass  # stored as plain for single-user VPS; encrypt later if needed
                execute(
                    """
                    UPDATE sender_profiles SET
                      sender_name=%s, company=%s, from_email=%s, reply_to=%s, domain=%s,
                      physical_address=%s, smtp_host=%s, smtp_port=%s, smtp_user=%s,
                      smtp_pass_enc=COALESCE(%s, smtp_pass_enc), daily_limit=%s,
                      send_window_start=%s, send_window_end=%s, timezone=%s
                    WHERE id=%s AND workspace_id=%s
                    """,
                    (
                        sn, company, from_email, reply_to, domain, addr,
                        smtp_host, smtp_port, smtp_user, pass_enc, daily,
                        wstart, wend, tz, s["id"], ws,
                    ),
                )
                st.success("Saved")
            test_to = st.text_input("Send test to", value=from_email, key=f"stestto_{s['id']}")
            if st.button("Send test email", key=f"stest_{s['id']}"):
                row = fetchone("SELECT * FROM sender_profiles WHERE id=%s", (s["id"],))
                try:
                    msg = EmailMessage()
                    msg["Subject"] = "Leadgensystem SMTP test"
                    msg["From"] = row["from_email"]
                    msg["To"] = test_to
                    msg.set_content(
                        f"SMTP test from Leadgensystem.\n\n{row.get('sender_name')}\n{row.get('physical_address') or ''}"
                    )
                    with smtplib.SMTP(row["smtp_host"], int(row["smtp_port"] or 587), timeout=20) as server:
                        server.starttls()
                        if row.get("smtp_user"):
                            server.login(row["smtp_user"], row.get("smtp_pass_enc") or "")
                        server.send_message(msg)
                    execute(
                        "UPDATE sender_profiles SET smtp_verified_at = %s WHERE id = %s",
                        (datetime.now(timezone.utc), s["id"]),
                    )
                    st.success("Test sent; SMTP marked verified")
                except Exception as exc:
                    st.error(f"SMTP test failed: {exc}")

    st.markdown("---")
    st.subheader("New sender profile")
    with st.form("new_sender"):
        ns_name = st.text_input("Sender name")
        ns_email = st.text_input("From email")
        if st.form_submit_button("Create"):
            execute(
                "INSERT INTO sender_profiles (workspace_id, sender_name, from_email) VALUES (%s,%s,%s)",
                (ws, ns_name, ns_email),
            )
            st.success("Created")
            st.rerun()

with tab_scoring:
    st.subheader("Scoring Profiles")
    profiles = fetchall("SELECT * FROM scoring_profiles WHERE workspace_id = %s", (ws,))
    for p in profiles:
        with st.expander(p["name"]):
            weights = p["weights"] if not isinstance(p["weights"], str) else json.loads(p["weights"])
            edited = {}
            cols = st.columns(3)
            for i, (k, v) in enumerate({**DEFAULT_WEIGHTS, **weights}.items()):
                edited[k] = cols[i % 3].number_input(k, 0, 30, int(v), key=f"scw_{p['id']}_{k}")
            if st.button("Save weights", key=f"scsave_{p['id']}"):
                execute(
                    "UPDATE scoring_profiles SET weights=%s::jsonb WHERE id=%s",
                    (json.dumps(edited), p["id"]),
                )
                st.success("Saved")

    with st.form("new_scoring"):
        nm = st.text_input("New scoring profile name")
        if st.form_submit_button("Create"):
            execute(
                "INSERT INTO scoring_profiles (workspace_id, name, weights) VALUES (%s,%s,%s::jsonb)",
                (ws, nm, json.dumps(DEFAULT_WEIGHTS)),
            )
            st.rerun()

with tab_account:
    st.subheader("Account")
    st.write(f"Signed in as **{user['email']}** · workspace `{ws}`")
    with st.form("change_pw"):
        cur = st.text_input("Current password", type="password")
        new = st.text_input("New password", type="password")
        if st.form_submit_button("Change password"):
            row = fetchone("SELECT password_hash FROM users WHERE id=%s", (user["id"],))
            if row and verify_password(cur, row["password_hash"]):
                execute(
                    "UPDATE users SET password_hash=%s WHERE id=%s",
                    (hash_password(new), user["id"]),
                )
                st.success("Password updated")
            else:
                st.error("Current password incorrect")
