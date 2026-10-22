"""Leadgensystem dashboard entrypoint."""
from __future__ import annotations

import streamlit as st

from dashboard.auth_ui import logout, render_login
from dashboard.ui import inject_css

st.set_page_config(page_title="Leadgensystem", layout="wide", initial_sidebar_state="expanded")
inject_css()

if "user" not in st.session_state:
    st.session_state["user"] = None

if not st.session_state.get("user"):
    render_login()
else:
    user = st.session_state["user"]
    with st.sidebar:
        st.markdown("### Leadgensystem")
        st.caption(user["email"])
        if st.button("Sign out"):
            logout()
            st.rerun()

    st.title("Leadgensystem")
    st.write(
        "Use the sidebar to open Overview, Leads, Campaigns, Campaign Builder, Outreach, Runs, or Settings."
    )
    st.info("Tip: start with **Campaign Builder** to create a campaign, then open **Leads**.")
