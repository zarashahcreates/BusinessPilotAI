"""Shared synthetic test data. Everything here is computer-generated, for tests only."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def small_sales() -> pd.DataFrame:
    """Hand-checkable dataset: Jan revenue 300 (cost 100), Feb 500 (cost 200), Mar 400 (cost 150)."""
    return pd.DataFrame({
        "Date": ["2025-01-10", "2025-01-20", "2025-02-05", "2025-02-25", "2025-03-03", "2025-03-31"],
        "Product": ["A", "B", "A", "B", "A", "B"],
        "Sales": [100, 200, 300, 200, 250, 150],
        "Expenses": [40, 60, 120, 80, 90, 60],
        "Quantity": [1, 2, 3, 2, 2, 1],
    })


def monthly_history(months: int = 36, seasonal: bool = True, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2022-01-01", periods=months, freq="MS")
    y = 1000 + 20 * np.arange(months) + (100 * np.sin(np.arange(months) * 2 * np.pi / 12) if seasonal else 0) + rng.normal(0, 25, months)
    return pd.DataFrame({"timestamp": ts, "revenue": y})


def daily_orders(start="2024-01-01", end="2025-12-31", seed=3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for d in pd.date_range(start, end, freq="D"):
        for p in ["Alpha", "Beta", "Gamma"]:
            rows.append({"Date": d, "Product": p, "Customer": f"C{rng.integers(1, 40)}", "Order ID": f"O{len(rows)}",
                         "Sales": float(rng.gamma(5, 40) * (1 + d.month / 20)), "Expenses": float(rng.gamma(5, 22)),
                         "Expense Category": ["Rent", "Stock", "Ads"][len(rows) % 3], "Quantity": int(rng.integers(1, 9))})
    return pd.DataFrame(rows)


def bundle_for(df: pd.DataFrame, currency: str = "Rs"):
    from businesspilot.pipeline import run_analysis
    from businesspilot.schema import detect_mapping
    return run_analysis(df, detect_mapping(df), currency)
