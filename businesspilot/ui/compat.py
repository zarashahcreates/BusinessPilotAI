"""Small helpers so the app works across Streamlit releases (``width='stretch'`` vs ``use_container_width``)."""
from __future__ import annotations

import streamlit as st

_MODE = {"new": None}


def stretch(fn, *args, **kwargs):
    """Call a Streamlit widget so it fills the container on both old and new Streamlit versions."""
    if _MODE["new"] is not False:
        try:
            out = fn(*args, width="stretch", **kwargs)
            _MODE["new"] = True
            return out
        except TypeError:
            _MODE["new"] = False
        except Exception as exc:  # noqa: BLE001 - older Streamlit raises StreamlitAPIException for the string width
            if "width" not in str(exc).lower():
                raise
            _MODE["new"] = False
    return fn(*args, use_container_width=True, **kwargs)


def plot(fig, key: str):
    return stretch(st.plotly_chart, fig, key=key, config={"displaylogo": False, "responsive": True})


def table(df, **kw):
    return stretch(st.dataframe, df, hide_index=True, **kw)


def button(label: str, **kw):
    return stretch(st.button, label, **kw)


def download(label: str, data: bytes, file_name: str, mime: str, key: str, **kw):
    return stretch(st.download_button, label, data, file_name=file_name, mime=mime, key=key, **kw)
