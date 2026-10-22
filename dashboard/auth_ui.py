"""Login form helpers."""
from __future__ import annotations

import streamlit as st

from common.auth import verify_password
from common.db import fetchone


def attempt_login(email: str, password: str) -> bool:
    row = fetchone(
        "SELECT id, email, password_hash, workspace_id, role FROM users WHERE email = %s",
        (email.strip().lower(),),
    )
    if not row:
        return False
    if not verify_password(password, row["password_hash"]):
        return False
    st.session_state["user"] = {
        "id": row["id"],
        "email": row["email"],
        "workspace_id": row["workspace_id"],
        "role": row["role"],
    }
    return True


def logout() -> None:
    st.session_state.pop("user", None)


def render_login() -> None:
    st.title("Leadgensystem")
    st.caption("Sign in to your workspace")
    with st.form("login_form"):
        email = st.text_input("Email", value="admin@local")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", type="primary")
        if submitted:
            if attempt_login(email, password):
                st.success("Signed in")
                st.rerun()
            else:
                st.error("Invalid email or password")
