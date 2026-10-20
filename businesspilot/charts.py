"""Interactive Plotly charts with one consistent visual style."""
from __future__ import annotations

from typing import Optional

import pandas as pd
import plotly.graph_objects as go

NAVY, BLUE, TEAL, AMBER, RED, SLATE = "#0B1F3A", "#2563EB", "#0D9488", "#D97706", "#DC2626", "#64748B"
PALETTE = [BLUE, TEAL, AMBER, "#7C3AED", RED, "#0891B2", SLATE, "#65A30D"]


def _layout(fig: go.Figure, title: str, ytitle: str = "", height: int = 380, legend: bool = True) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, x=0, xanchor="left", font=dict(size=16, color=NAVY)),
        height=height, margin=dict(l=10, r=10, t=60, b=10),
        template="plotly_white", font=dict(family="Inter, Segoe UI, Arial", size=12, color="#334155"),
        hovermode="x unified", showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        yaxis=dict(title=ytitle, gridcolor="#E2E8F0", zeroline=False, tickformat="~s"),
        xaxis=dict(showgrid=False, automargin=True),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def trend_chart(monthly: pd.DataFrame, currency: str = "") -> Optional[go.Figure]:
    if monthly.empty or "revenue" not in monthly:
        return None
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=monthly["timestamp"], y=monthly["revenue"], name="Revenue", mode="lines+markers",
                             line=dict(color=BLUE, width=3), hovertemplate="%{y:,.2f}"))
    if "expenses" in monthly and monthly["expenses"].notna().any():
        fig.add_trace(go.Scatter(x=monthly["timestamp"], y=monthly["expenses"], name="Expenses", mode="lines",
                                 line=dict(color=AMBER, width=2), hovertemplate="%{y:,.2f}"))
    if "calc_profit" in monthly and monthly["calc_profit"].notna().any():
        fig.add_trace(go.Scatter(x=monthly["timestamp"], y=monthly["calc_profit"], name="Profit", mode="lines",
                                 line=dict(color=TEAL, width=2), hovertemplate="%{y:,.2f}"))
    return _layout(fig, "Revenue, expenses and profit by month", currency)


def period_bars(monthly: pd.DataFrame, freq: str = "Monthly", currency: str = "") -> Optional[go.Figure]:
    if monthly.empty or "revenue" not in monthly:
        return None
    m = monthly[["timestamp", "revenue"]].copy()
    if freq == "Quarterly":
        m["label"] = m["timestamp"].dt.to_period("Q").astype(str)
        m = m.groupby("label", as_index=False)["revenue"].sum(min_count=1)
        x = m["label"]
    else:
        x = m["timestamp"]
    fig = go.Figure(go.Bar(x=x, y=m["revenue"], marker_color=BLUE, hovertemplate="%{y:,.2f}"))
    if freq == "Quarterly":
        fig.update_xaxes(type="category")
    return _layout(fig, f"{freq} sales", currency, legend=False)


def product_bar(products: pd.DataFrame, value_col: str = "revenue", currency: str = "") -> Optional[go.Figure]:
    if products.empty:
        return None
    d = products.iloc[::-1]
    fig = go.Figure(go.Bar(x=d[value_col], y=d["product"].astype(str), orientation="h", marker_color=BLUE,
                           customdata=d["share"], hovertemplate="%{x:,.2f} (%{customdata:.1%} of total)<extra></extra>"))
    fig = _layout(fig, f"Top products by {value_col}", legend=False, height=max(300, 36 * len(d) + 110))
    fig.update_layout(hovermode="closest", xaxis=dict(title=currency, gridcolor="#E2E8F0", tickformat="~s"), yaxis=dict(title="", autorange=True))
    return fig


def expense_chart(expenses: pd.DataFrame, currency: str = "") -> Optional[go.Figure]:
    if expenses.empty:
        return None
    d = expenses.iloc[::-1]
    fig = go.Figure(go.Bar(x=d["expenses"], y=d["category"].astype(str), orientation="h", marker_color=AMBER,
                           customdata=d["share"], hovertemplate="%{x:,.2f} (%{customdata:.1%} of expenses)<extra></extra>"))
    fig = _layout(fig, "Expenses by category", legend=False, height=max(300, 36 * len(d) + 110))
    fig.update_layout(hovermode="closest", xaxis=dict(title=currency, gridcolor="#E2E8F0", tickformat="~s"))
    return fig


def customer_chart(cm: pd.DataFrame) -> Optional[go.Figure]:
    if cm.empty:
        return None
    fig = go.Figure()
    fig.add_trace(go.Bar(x=cm["timestamp"], y=cm["New customers"], name="New", marker_color=TEAL))
    fig.add_trace(go.Bar(x=cm["timestamp"], y=cm["Returning customers"], name="Returning", marker_color=BLUE))
    fig.update_layout(barmode="stack")
    return _layout(fig, "Active customers by month (first-time vs returning)", "Customers")


def forecast_figure(fc, currency: str = "") -> Optional[go.Figure]:
    if fc is None or not getattr(fc, "available", False):
        return None
    h, f = fc.history, fc.forecast
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=h["timestamp"], y=h["value"], name="Actual", mode="lines+markers", line=dict(color=BLUE, width=3)))
    fig.add_trace(go.Scatter(x=list(f["timestamp"]) + list(f["timestamp"][::-1]), y=list(f["upper"]) + list(f["lower"][::-1]),
                             fill="toself", fillcolor="rgba(13,148,136,0.15)", line=dict(width=0), hoverinfo="skip",
                             name=f"{int(fc.interval_level*100)}% prediction interval"))
    fig.add_trace(go.Scatter(x=f["timestamp"], y=f["point"], name="Forecast", mode="lines+markers", line=dict(color=TEAL, width=3, dash="dash"),
                             hovertemplate="%{y:,.2f}"))
    interp = h[h["interpolated"]]
    if not interp.empty:
        fig.add_trace(go.Scatter(x=interp["timestamp"], y=interp["value"], name="Filled gap (interpolated)", mode="markers",
                                 marker=dict(color=RED, size=9, symbol="x")))
    return _layout(fig, f"Monthly {fc.target}: history and forecast", currency)


def actual_vs_predicted(fc, currency: str = "") -> Optional[go.Figure]:
    if fc is None or not getattr(fc, "available", False) or fc.backtest.empty:
        return None
    b = fc.backtest
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=b["timestamp"], y=b["actual"], name="Actual", mode="lines+markers", line=dict(color=BLUE, width=3)))
    fig.add_trace(go.Scatter(x=b["timestamp"], y=b["predicted"], name="Predicted (using only earlier months)", mode="lines+markers",
                             line=dict(color=AMBER, width=2, dash="dot")))
    return _layout(fig, "Back-test: actual versus predicted", currency)


def missing_chart(per_column: pd.DataFrame) -> Optional[go.Figure]:
    d = per_column[per_column["missing %"] > 0].sort_values("missing %")
    if d.empty:
        return None
    fig = go.Figure(go.Bar(x=d["missing %"], y=d["column"], orientation="h", marker_color=RED, hovertemplate="%{x:.1f}% blank<extra></extra>"))
    fig = _layout(fig, "Blank cells by column (%)", legend=False, height=max(260, 32 * len(d) + 110))
    fig.update_layout(hovermode="closest")
    return fig
