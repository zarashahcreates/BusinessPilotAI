"""One entry point that turns a raw table + column mapping into every result the UI and reports need."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from . import metrics as M
from .ai_insights import InsightReport, build_insights
from .forecasting import ForecastResult, forecast_series, risk_indicators
from .schema import Mapping, Quality, Standardized, apply_mapping, assess_quality


@dataclass
class Bundle:
    std: Standardized
    data: pd.DataFrame                 # standardised AND filtered
    currency: str
    period: str
    avail: dict
    metrics: list[M.Metric]
    monthly: pd.DataFrame
    products: pd.DataFrame
    products_qty: pd.DataFrame
    expenses: pd.DataFrame
    anomalies: list[dict]
    drivers: Optional[dict]
    quality: Quality
    risk: list[dict]
    forecast: Optional[ForecastResult]
    insights: InsightReport
    filters_note: str = ""


def fingerprint(df: pd.DataFrame, *extra) -> str:
    """Stable hash of a table plus settings; used to avoid recomputing on Streamlit reruns."""
    h = hashlib.sha256()
    h.update(pd.util.hash_pandas_object(df, index=True).values.tobytes())
    h.update(str(list(df.columns)).encode())
    for e in extra:
        h.update(repr(e).encode())
    return h.hexdigest()


def run_analysis(raw: pd.DataFrame, mapping: Mapping, currency: str = "", date_range=None,
                 category_filters: dict | None = None, horizon: int = 6) -> Bundle:
    std = apply_mapping(raw, mapping)
    full = std.df
    quality = assess_quality(raw, std)
    data = M.apply_filters(full, date_range, category_filters)
    filters_note = ""
    if len(data) != len(full):
        filters_note = f"Filters applied: showing {len(data):,} of {len(full):,} rows."
    avail = M.available_analyses(data)
    metrics = M.core_metrics(data, currency)
    monthly = M.monthly_frame(data)
    products = M.top_products(data, 10, "revenue") if M.has(data, "revenue") else M.top_products(data, 10, "quantity")
    products_qty = M.top_products(data, 10, "quantity")
    expenses = M.expense_breakdown(data)
    anomalies = M.find_anomalies(monthly, "revenue")
    drivers = M.driver_analysis(data, "product")
    risk = risk_indicators(monthly)
    fc = None
    if avail["revenue"] and M.has(data, "date"):
        src_end = data["date"].max()
        fc = forecast_series(monthly, "revenue", horizon, source_end=src_end)
    ins = build_insights(metrics, monthly, products, expenses, anomalies, drivers, quality.issues, fc, risk, currency)
    return Bundle(std, data, currency, M.period_label(data), avail, metrics, monthly, products, products_qty, expenses,
                  anomalies, drivers, quality, risk, fc, ins, filters_note)
