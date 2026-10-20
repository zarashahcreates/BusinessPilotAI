import os

import pandas as pd
import streamlit as st

from businesspilot.state import REPORT_TYPES, set_workspace

st.title("Settings")
st.caption("These values travel with the workspace for mapping, narrative tone, and export headings.")

st.session_state.business_name = st.text_input("Business name", value=st.session_state.business_name)
st.session_state.currency = st.text_input("Currency label", value=st.session_state.currency, help="Display label only. The app does not convert currencies.")
st.session_state.report_type = st.selectbox(
    "Report type",
    REPORT_TYPES,
    index=REPORT_TYPES.index(st.session_state.report_type) if st.session_state.report_type in REPORT_TYPES else 0,
)
st.session_state.period_label = st.text_input("Reporting period", value=st.session_state.period_label)
st.session_state.detail = st.selectbox(
    "Narrative length",
    ["Concise", "Standard", "Detailed"],
    index=["Concise", "Standard", "Detailed"].index(st.session_state.detail)
    if st.session_state.detail in {"Concise", "Standard", "Detailed"}
    else 1,
)
st.session_state.include_recommendations = st.toggle("Include recommendations", value=bool(st.session_state.include_recommendations))

st.subheader("AI connection")
key_present = bool(os.getenv("OPENAI_API_KEY"))
if key_present:
    st.badge("API key loaded from environment", icon=":material/check_circle:", color="green")
    st.caption(f"Model: {os.getenv('OPENAI_MODEL', 'gpt-4.1-mini')}")
else:
    st.badge("Local summaries only", icon=":material/lock:", color="orange")
    st.caption("Copy `.env.example` to `.env` and add OPENAI_API_KEY to enable model-written narrative and Q&A.")

st.subheader("Privacy")
st.markdown(
    """
This app processes uploads in the running session. If an API key is configured, only the summary
payload sent to that provider leaves the machine. Do not upload data you are not authorised to process.
"""
)

st.subheader("Reset")
if st.button("Clear workspace and chat", icon=":material/restart_alt:"):
    set_workspace(pd.DataFrame(), [])
    st.session_state.report_library = []
    st.success("Workspace cleared.")
    st.rerun()
