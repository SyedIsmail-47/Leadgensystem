"""Shared Streamlit UI helpers."""
from __future__ import annotations

import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: Inter, system-ui, sans-serif; }
[data-testid="stMetricValue"] { font-variant-numeric: tabular-nums; }
.chip {
  display:inline-block; padding:2px 8px; border-radius:6px; font-size:12px;
  border:1px solid #E3E6EB; margin-right:4px;
}
.chip-a { background:#DCFCE7; color:#16A34A; border-color:#86EFAC; }
.chip-b { background:#FEF3C7; color:#D97706; border-color:#FCD34D; }
.chip-c { background:#F1F5F9; color:#64748B; border-color:#CBD5E1; }
.chip-stage { background:#fff; color:#14171F; }
.card {
  background:#FFFFFF; border:1px solid #E3E6EB; border-radius:10px;
  padding:16px; margin-bottom:12px;
}
.score-bar { height:6px; background:#E3E6EB; border-radius:4px; overflow:hidden; }
.score-bar > div { height:100%; background:#2563EB; }
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def require_login() -> dict:
    from dashboard.auth_ui import render_login

    if "user" not in st.session_state:
        st.session_state["user"] = None
    user = st.session_state.get("user")
    if not user:
        render_login()
        st.stop()
    return user


def tier_chip(tier: str | None) -> str:
    t = (tier or "C").upper()
    cls = {"A": "chip-a", "B": "chip-b", "C": "chip-c"}.get(t, "chip-c")
    return f'<span class="chip {cls}">Tier {t}</span>'


def stage_chip(stage: str | None) -> str:
    return f'<span class="chip chip-stage">{stage or "new"}</span>'


def score_bar(score: int | None) -> str:
    s = int(score or 0)
    return (
        f'<div style="min-width:80px"><strong>{s}</strong>'
        f'<div class="score-bar"><div style="width:{s}%"></div></div></div>'
    )


def confirm_box(key: str, label: str = "I confirm this destructive action") -> bool:
    return st.checkbox(label, key=key)
