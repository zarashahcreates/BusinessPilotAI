"""Static (matplotlib) charts used inside PDF and DOCX reports. The interactive app uses Plotly instead."""
from __future__ import annotations

import io
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402
import pandas as pd  # noqa: E402

NAVY, BLUE, TEAL, AMBER, RED, GREY = "#0B1F3A", "#2563EB", "#0D9488", "#D97706", "#DC2626", "#94A3B8"


def _fmt(ax, axis="y"):
    f = mticker.FuncFormatter(lambda v, _: f"{v/1e6:.1f}M" if abs(v) >= 1e6 else f"{v/1e3:.0f}K" if abs(v) >= 1e4 else f"{v:,.0f}")
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(f)


def _png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def _style(ax, title: str, ylabel: str = ""):
    ax.set_title(title, loc="left", fontsize=11, fontweight="bold", color=NAVY)
    ax.set_ylabel(ylabel, fontsize=9, color="#475569")
    ax.grid(axis="y", alpha=0.25)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(labelsize=8)


def trend_chart(monthly: pd.DataFrame, currency: str = "") -> Optional[bytes]:
    if monthly.empty or "revenue" not in monthly:
        return None
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    ax.plot(monthly["timestamp"], monthly["revenue"], color=BLUE, lw=2, label="Revenue")
    if "expenses" in monthly and monthly["expenses"].notna().any():
        ax.plot(monthly["timestamp"], monthly["expenses"], color=AMBER, lw=2, label="Expenses")
    if "calc_profit" in monthly and monthly["calc_profit"].notna().any():
        ax.plot(monthly["timestamp"], monthly["calc_profit"], color=TEAL, lw=2, label="Profit")
    _style(ax, "Monthly revenue, expenses and profit", currency)
    _fmt(ax)
    ax.legend(frameon=False, fontsize=8, ncol=3, loc="upper left")
    fig.autofmt_xdate()
    return _png(fig)


def bar_chart(df: pd.DataFrame, label_col: str, value_col: str, title: str, currency: str = "", n: int = 8) -> Optional[bytes]:
    if df.empty:
        return None
    d = df.head(n).iloc[::-1]
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    ax.barh([str(x)[:28] for x in d[label_col]], d[value_col], color=BLUE)
    _style(ax, title, "")
    ax.grid(axis="x", alpha=0.25); ax.grid(axis="y", alpha=0)
    _fmt(ax, "x")
    return _png(fig)


def forecast_chart(fc, currency: str = "") -> Optional[bytes]:
    if fc is None or not getattr(fc, "available", False):
        return None
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    h, f = fc.history, fc.forecast
    ax.plot(h["timestamp"], h["value"], color=BLUE, lw=2, label="Actual")
    if not fc.backtest.empty:
        ax.plot(fc.backtest["timestamp"], fc.backtest["predicted"], color=GREY, lw=1.2, ls=":", label="Back-test predictions")
    ax.plot(f["timestamp"], f["point"], color=TEAL, lw=2, ls="--", label="Forecast")
    ax.fill_between(f["timestamp"], f["lower"], f["upper"], color=TEAL, alpha=0.18,
                    label=f"{int(fc.interval_level*100)}% prediction interval")
    _style(ax, f"Monthly {fc.target} — history and forecast", currency)
    _fmt(ax)
    ax.legend(frameon=False, fontsize=8, ncol=2, loc="upper left")
    fig.autofmt_xdate()
    return _png(fig)
