r"""BusinessPilot AI — Streamlit entry point.

Run (Windows PowerShell, from this folder):
    .\.venv\Scripts\python.exe -m streamlit run app.py
"""
import sys
import traceback

import streamlit as st

st.set_page_config(page_title="BusinessPilot AI", page_icon="📈", layout="wide", initial_sidebar_state="expanded")

try:
    from dotenv import load_dotenv
    load_dotenv()          # reads .env if present; secrets never live in source code
except ImportError:
    pass

from businesspilot import config, ingestion
from businesspilot.ui import pages_analysis as PA, pages_data as PD, state, theme

LABELS = {"Home": "Home", "Upload": "1 · Upload data", "Review": "2 · Review data", "Analyze": "3 · Analyze",
          "Insights": "4 · Insights", "Reports": "5 · Reports", "History": "Saved analyses"}
RENDER = {"Home": PD.render_home, "Upload": PD.render_upload, "Review": PD.render_review, "Analyze": PA.render_analyze,
          "Insights": PA.render_insights, "Reports": PA.render_reports, "History": PD.render_history}


def sidebar() -> None:
    s = st.session_state
    with st.sidebar:
        st.markdown('<div class="bp-brand">BusinessPilot <span>AI</span></div><div class="bp-tag">Business analysis made simple</div>', unsafe_allow_html=True)
        st.radio("Navigate", state.PAGES, format_func=LABELS.get, key="nav", label_visibility="collapsed")
        st.divider()
        if state.has_data():
            st.caption(f"Dataset loaded: {len(s.raw):,} rows")
            if s.analysis_id is not None:
                st.caption(f"Saved as “{s.analysis_name}”" + ("" if s.saved_fp == s.raw_fp else " (changes not saved)"))
            else:
                st.caption("Not saved yet")
        else:
            st.caption("No data loaded")
        with st.expander("Settings"):
            st.text_input("Business name", key="business_name")
            st.text_input("Currency label", max_chars=6, key="currency", help="Shown next to money values, e.g. Rs, $, EUR.")
        ai = "on" if config.openai_key() else "off (no API key)"
        st.caption(f"AI commentary: {ai}")
        st.caption("Your data stays in this app. It is only sent to an AI service if you click the AI commentary button.")


def main() -> None:
    state.init()
    if st.session_state.pop("pending_reset", False):
        state.reset_all()
    theme.inject()
    sidebar()
    page = st.session_state.nav
    try:
        RENDER[page]()
    except Exception as exc:  # noqa: BLE001 - never show a raw stack trace to end users
        traceback.print_exc(file=sys.stderr)
        st.error(f"Something went wrong on this page ({type(exc).__name__}). Your data is still loaded — try another page or reload. "
                 "If it keeps happening, see Troubleshooting in the README.")


main()
