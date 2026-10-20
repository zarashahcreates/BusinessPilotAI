from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import streamlit as st


def save_report(entry: dict[str, Any]) -> None:
    library = list(st.session_state.get("report_library") or [])
    item = {
        "saved_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        **entry,
    }
    library.insert(0, item)
    st.session_state.report_library = library[:25]


def library() -> list[dict[str, Any]]:
    return list(st.session_state.get("report_library") or [])
