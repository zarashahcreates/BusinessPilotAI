from __future__ import annotations

import math
from typing import Any

import pandas as pd


def money(value: Any, currency: str = "Rs") -> str:
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{currency} {number:,.2f}"


def compact_number(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    abs_number = abs(number)
    if abs_number >= 1_000_000_000:
        return f"{number / 1_000_000_000:.2f}B"
    if abs_number >= 1_000_000:
        return f"{number / 1_000_000:.2f}M"
    if abs_number >= 1_000:
        return f"{number / 1_000:.1f}K"
    if abs_number >= 100:
        return f"{number:,.0f}"
    return f"{number:,.2f}"


def percent(value: Any, digits: int = 1) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    try:
        return f"{float(value):.{digits}f}%"
    except (TypeError, ValueError):
        return "—"


def slug_filename(text: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_ " else "" for ch in str(text))
    return "_".join(cleaned.strip().split()) or "businesspilot"
