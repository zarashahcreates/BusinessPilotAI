"""Session-state management. All user data lives in ``st.session_state`` (per browser session),
never in a cache shared between users."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import ingestion
from ..pipeline import Bundle, fingerprint, run_analysis
from ..schema import Mapping, detect_mapping

PAGES = ["Home", "Upload", "Review", "Analyze", "Insights", "Reports", "History"]

DEFAULTS = {
    "nav": "Home", "results": [], "result_keys": [], "manual_df": None, "raw": None, "raw_fp": None, "mapping": None,
    "business_name": "My Business", "currency": "", "horizon": 6, "date_range": None, "cat_filters": {},
    "memo": {}, "analysis_id": None, "analysis_name": "", "saved_fp": None, "exports": None, "exports_key": None,
    "confirm_new": False, "prob_result": None, "demo": False, "mapping_confirmed": False, "flash": None,
}


def init() -> None:
    for k, v in DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = v.copy() if isinstance(v, (dict, list)) else v


def go(page: str) -> None:
    """Callback for navigation buttons (runs before the next rerun, so it may set the radio's value)."""
    st.session_state["nav"] = page


def has_data() -> bool:
    raw = st.session_state.raw
    return raw is not None and not raw.empty


def rebuild_raw(keep_mapping: bool = False) -> None:
    """Merge uploaded tables + manual entry into one raw table and reset anything derived from it."""
    frames = [r for r in st.session_state.results if r.ok]
    parts = ingestion.combine_tables(frames)
    manual = st.session_state.manual_df
    if manual is not None and not manual.empty:
        m = manual.copy(); m["source_file"] = "Manual entry"
        parts = pd.concat([parts, m], ignore_index=True, sort=False) if not parts.empty else m
    if parts is None or parts.empty:
        st.session_state.raw, st.session_state.raw_fp = None, None
        st.session_state.mapping = None
    else:
        parts = parts.reset_index(drop=True)
        fp = fingerprint(parts)
        if fp != st.session_state.raw_fp or not keep_mapping:
            st.session_state.raw, st.session_state.raw_fp = parts, fp
            st.session_state.mapping = detect_mapping(parts.drop(columns=["source_file"], errors="ignore"))
            st.session_state.mapping_confirmed = False
            st.session_state.date_range, st.session_state.cat_filters = None, {}
            for k in [k for k in st.session_state.keys() if k.startswith(("map_", "flt_"))]:
                del st.session_state[k]
    st.session_state.memo, st.session_state.exports, st.session_state.exports_key = {}, None, None


def reset_all() -> None:
    for k, v in DEFAULTS.items():
        if k in ("business_name", "currency", "horizon"):
            continue
        st.session_state[k] = v.copy() if isinstance(v, (dict, list)) else v
    # Clearing widget keys makes uploader/editor widgets start empty.
    for k in list(st.session_state.keys()):
        if k.startswith(("w_", "map_", "flt_")):
            del st.session_state[k]
    st.session_state["uploader_version"] = st.session_state.get("uploader_version", 0) + 1


def analysis_inputs() -> tuple:
    s = st.session_state
    return (s.raw_fp, tuple(sorted((s.mapping.columns if s.mapping else {}).items())), s.currency, s.date_range,
            tuple(sorted((k, tuple(v)) for k, v in s.cat_filters.items())), s.horizon)


def current_bundle() -> Bundle | None:
    """Compute (or reuse) the analysis for the current data and settings. Memoised per session."""
    s = st.session_state
    if not has_data() or s.mapping is None:
        return None
    key = analysis_inputs()
    memo = s.memo
    if memo.get("key") != key:
        with st.spinner("Analyzing your data…"):
            raw = s.raw.drop(columns=["source_file"], errors="ignore")
            bundle = run_analysis(raw, s.mapping, s.currency, s.date_range, s.cat_filters, s.horizon)
        s.memo = {"key": key, "bundle": bundle}
        s.exports, s.exports_key = None, None
    return s.memo["bundle"]


def done_steps() -> set[str]:
    s, done = st.session_state, set()
    if has_data():
        done.add("Upload")
    if has_data() and s.mapping_confirmed:
        done |= {"Review"}
    if s.memo.get("bundle") is not None and s.mapping_confirmed:
        done.add("Analyze")
    if s.exports:
        done |= {"Insights", "Report"}
    return done
