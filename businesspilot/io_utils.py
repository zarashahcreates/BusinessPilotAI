"""Backward-compatible wrappers around :mod:`businesspilot.ingestion` (kept for older imports)."""
from __future__ import annotations

import pandas as pd

from .ingestion import IngestResult, combine_tables as _combine, load_file, parse_manual_data  # noqa: F401


def load_uploaded_file(uploaded_file):
    """Return (DataFrame or None, note) for a Streamlit UploadedFile-like object."""
    res = load_file(uploaded_file.name, uploaded_file.getvalue())
    if res.level == "error":
        raise ValueError(res.note)
    return (res.table if res.ok else None), res.note


def combine_tables(tables, manual_df=None):
    usable = [t.copy() for t in (tables or []) if t is not None and not t.empty]
    if manual_df is not None and not manual_df.empty:
        usable.append(manual_df.copy())
    return pd.concat(usable, ignore_index=True, sort=False) if usable else pd.DataFrame()
