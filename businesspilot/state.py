from __future__ import annotations

import pandas as pd
import streamlit as st

from businesspilot.mapping import infer_column_roles, sanitize_roles

REPORT_TYPES = [
    "Auto-detect",
    "Financial performance",
    "Sales performance",
    "Inventory",
    "Customer analysis",
    "General business report",
]


def init_session() -> None:
    st.session_state.setdefault("business_name", "My business")
    st.session_state.setdefault("currency", "Rs")
    st.session_state.setdefault("report_type", "Auto-detect")
    st.session_state.setdefault("period_label", "Current period")
    st.session_state.setdefault("detail", "Standard")
    st.session_state.setdefault("include_recommendations", True)
    st.session_state.setdefault("workspace_df", pd.DataFrame())
    st.session_state.setdefault("source_notes", [])
    st.session_state.setdefault("column_roles", {})
    st.session_state.setdefault("narrative", None)
    st.session_state.setdefault("model_result", None)
    st.session_state.setdefault("chat_messages", [])
    st.session_state.setdefault("report_library", [])
    st.session_state.setdefault("last_sample", None)


def current_data() -> pd.DataFrame:
    frame = st.session_state.get("workspace_df")
    if frame is None:
        return pd.DataFrame()
    return frame


def has_data() -> bool:
    return not current_data().empty


def set_workspace(
    df: pd.DataFrame,
    notes: list[str] | None = None,
    sample_name: str | None = None,
    *,
    preserve_roles: bool = False,
) -> None:
    previous_roles = st.session_state.get("column_roles")
    st.session_state.workspace_df = df.copy() if df is not None else pd.DataFrame()
    st.session_state.source_notes = notes or []
    if preserve_roles:
        st.session_state.column_roles = sanitize_roles(st.session_state.workspace_df, previous_roles)
    else:
        st.session_state.column_roles = infer_column_roles(st.session_state.workspace_df)
    st.session_state.narrative = None
    st.session_state.model_result = None
    st.session_state.chat_messages = []
    st.session_state.last_sample = sample_name


def append_workspace(df: pd.DataFrame, note: str) -> None:
    from businesspilot.io_utils import combine_tables

    existing = current_data()
    combined = combine_tables([existing, df])
    notes = list(st.session_state.get("source_notes") or [])
    notes.append(note)
    set_workspace(combined, notes, sample_name=st.session_state.get("last_sample"))


def roles() -> dict[str, str | None]:
    return sanitize_roles(current_data(), st.session_state.get("column_roles"))


def require_data(message: str = "Load a dataset in Data studio first.") -> pd.DataFrame:
    data = current_data()
    if data.empty:
        st.info(message, icon=":material/info:")
        st.page_link("app_pages/data_studio.py", label="Open data studio", icon=":material/upload_file:")
        st.stop()
    return data
