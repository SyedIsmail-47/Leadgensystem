from __future__ import annotations

import streamlit as st

from dashboard.ui import inject_css, require_login

st.set_page_config(page_title="Outreach", layout="wide")
inject_css()
require_login()
st.title("Outreach")
st.info("Outreach approval and sending land in M6. Profiles are managed in Settings.")
