"""Thin wrapper so the app still starts (with a clear message) if Plotly is missing."""
from __future__ import annotations

import streamlit as st

from .compat import plot

try:
    from .. import charts as _charts
    PLOTLY_OK = True
except ImportError:  # pragma: no cover - depends on environment
    _charts = None
    PLOTLY_OK = False


def show(fig, key: str) -> None:
    if not PLOTLY_OK:
        st.warning("Charts need the 'plotly' package: run  pip install -r requirements.txt")
    elif fig is not None:
        plot(fig, key)


def missing(per_column):
    return _charts.missing_chart(per_column) if PLOTLY_OK else None


def __getattr__(name):  # expose chart builders lazily: charts_ui.trend_chart(...)
    if _charts is None:
        return lambda *a, **k: None
    return getattr(_charts, name)
