"""Deterministic business calculations. All numbers shown to the user come from this module.

Every function works on a *standardised* frame (columns named after roles such as ``revenue``,
``expenses``, ``date``) produced by :func:`businesspilot.schema.apply_mapping`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class Metric:
    key: str
    label: str
    value: Optional[float]
    display: str
    formula: str = ""
    explanation: str = ""
    basis: str = ""          # period / units / assumptions
    tone: str = "neutral"    # good | bad | neutral

    def as_row(self) -> dict:
        return {"Metric": self.label, "Value": self.display, "Formula": self.formula, "Basis": self.basis}


def money(v: float | None, currency: str = "") -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "n/a"
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1e9:
        s = f"{v/1e9:,.2f}B"
    elif v >= 1e6:
        s = f"{v/1e6:,.2f}M"
    elif v >= 1e5:
        s = f"{v:,.0f}"
    else:
        s = f"{v:,.2f}"
    return f"{sign}{currency} {s}".strip() if currency else f"{sign}{s}"


def pct(v: float | None, digits: int = 1) -> str:
    return "n/a" if v is None or np.isnan(v) else f"{v*100:.{digits}f}%"


def has(df: pd.DataFrame, role: str) -> bool:
    return role in df.columns and df[role].notna().any()


def available_analyses(df: pd.DataFrame) -> dict[str, bool]:
    """What can honestly be analysed given the mapped columns."""
    dated = has(df, "date")
    n_periods = 0
    if dated:
        n_periods = df["date"].dropna().dt.to_period("M").nunique()
    out = {
        "revenue": has(df, "revenue"),
        "expenses": has(df, "expenses") or has(df, "cogs"),
        "profit": has(df, "profit") or (has(df, "revenue") and (has(df, "expenses") or has(df, "cogs"))),
        "time": dated and n_periods >= 2,
        "products": has(df, "product") and (has(df, "revenue") or has(df, "quantity")),
        "customers": has(df, "customer") or has(df, "order_id"),
        "marketing": has(df, "marketing_spend") or (has(df, "clicks") and has(df, "impressions")),
        "inventory": has(df, "stock"),
        "expense_breakdown": has(df, "expenses") and has(df, "category"),
        "forecast": has(df, "revenue") and dated and n_periods >= 12,
    }
    return {k: bool(v) for k, v in out.items()}


def apply_filters(df: pd.DataFrame, date_range=None, categories: dict[str, list] | None = None) -> pd.DataFrame:
    out = df
    if date_range and has(out, "date"):
        lo, hi = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
        out = out[(out["date"] >= lo) & (out["date"] <= hi + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))]
    for col, vals in (categories or {}).items():
        if col in out.columns and vals:
            out = out[out[col].isin(vals)]
    return out


def period_label(df: pd.DataFrame) -> str:
    if not has(df, "date"):
        return "All rows (no date column mapped)"
    d = df["date"].dropna()
    return f"{d.min():%d %b %Y} – {d.max():%d %b %Y}"


def _sum(df: pd.DataFrame, role: str) -> float:
    return float(df[role].sum(skipna=True)) if has(df, role) else 0.0


def profit_components(df: pd.DataFrame) -> dict:
    """Work out which profit definition is possible. Never fabricates missing cost inputs."""
    rev = _sum(df, "revenue") if has(df, "revenue") else None
    cogs = _sum(df, "cogs") if has(df, "cogs") else None
    exp = _sum(df, "expenses") if has(df, "expenses") else None
    out = {"revenue": rev, "cogs": cogs, "expenses": exp, "gross_profit": None, "net_profit": None,
           "net_formula": "", "source": ""}
    if rev is not None and cogs is not None:
        out["gross_profit"] = rev - cogs
    if rev is not None and (cogs is not None or exp is not None):
        out["net_profit"] = rev - (cogs or 0.0) - (exp or 0.0)
        parts = ["Revenue"] + (["COGS"] if cogs is not None else []) + (["Expenses"] if exp is not None else [])
        out["net_formula"] = parts[0] + "".join(f" − {p}" for p in parts[1:])
        out["source"] = "calculated"
    elif has(df, "profit"):
        out["net_profit"] = _sum(df, "profit")
        out["net_formula"] = "Sum of the profit column"
        out["source"] = "reported"
    return out


def core_metrics(df: pd.DataFrame, currency: str = "") -> list[Metric]:
    basis = period_label(df)
    ms: list[Metric] = []
    pc = profit_components(df)
    if pc["revenue"] is not None:
        ms.append(Metric("revenue", "Total revenue", pc["revenue"], money(pc["revenue"], currency),
                         "Sum of revenue", "All income from sales before any costs are taken off.", basis))
    if pc["expenses"] is not None:
        ms.append(Metric("expenses", "Total expenses", pc["expenses"], money(pc["expenses"], currency),
                         "Sum of expenses", "Money spent running the business.", basis, "neutral"))
    if pc["cogs"] is not None:
        ms.append(Metric("cogs", "Cost of goods sold", pc["cogs"], money(pc["cogs"], currency),
                         "Sum of COGS", "Direct cost of the products you sold.", basis))
    if pc["gross_profit"] is not None:
        ms.append(Metric("gross_profit", "Gross profit", pc["gross_profit"], money(pc["gross_profit"], currency),
                         "Revenue − COGS", "What is left after paying for the goods you sold.", basis,
                         "good" if pc["gross_profit"] > 0 else "bad"))
    if pc["net_profit"] is not None:
        assumption = ("Assumes the expenses column covers all other costs." if pc["source"] == "calculated" else "Uses the profit column as provided.")
        ms.append(Metric("net_profit", "Net profit" if pc["source"] else "Profit", pc["net_profit"], money(pc["net_profit"], currency),
                         pc["net_formula"], "What the business actually keeps after costs. Negative means a loss.",
                         f"{basis}. {assumption}", "good" if pc["net_profit"] > 0 else "bad"))
        if pc["revenue"] and pc["revenue"] > 0:
            margin = pc["net_profit"] / pc["revenue"]
            ms.append(Metric("margin", "Profit margin", margin, pct(margin), "Net profit ÷ Revenue",
                             "Out of every 100 of sales, how much is kept as profit. Different from growth, which compares periods.",
                             basis, "good" if margin > 0 else "bad"))
    g = growth_metrics(df)
    if g:
        ms.append(Metric("growth", "Revenue growth", g["growth"], pct(g["growth"]),
                         "(Latest period − Previous period) ÷ Previous period",
                         "How much sales changed versus the period before.", g["basis"],
                         "good" if g["growth"] > 0 else "bad"))
    if has(df, "quantity"):
        q = _sum(df, "quantity")
        ms.append(Metric("quantity", "Units sold", q, f"{q:,.0f}", "Sum of quantity", "Total number of items sold.", basis))
    ms.extend(customer_metrics(df, currency))
    ms.extend(marketing_metrics(df, currency))
    ms.extend(inventory_metrics(df))
    return ms


def monthly_frame(df: pd.DataFrame, freq: str = "M") -> pd.DataFrame:
    """Aggregate to calendar periods. Rows without a valid date are excluded (and reported elsewhere)."""
    if not has(df, "date"):
        return pd.DataFrame()
    d = df.dropna(subset=["date"]).copy()
    if d.empty:
        return pd.DataFrame()
    d["period"] = d["date"].dt.to_period(freq)
    cols = [c for c in ("revenue", "expenses", "cogs", "profit", "quantity", "marketing_spend") if has(d, c)]
    if not cols:
        return pd.DataFrame()
    g = d.groupby("period")[cols].sum(min_count=1)
    # Include empty periods so gaps stay visible instead of being silently skipped.
    full = pd.period_range(g.index.min(), g.index.max(), freq=freq)
    g = g.reindex(full)
    g.index.name = "period"
    if "revenue" in g and ("expenses" in g or "cogs" in g):
        g["calc_profit"] = g["revenue"].fillna(0) - g.get("cogs", 0).fillna(0) if "cogs" in g else g["revenue"]
        if "expenses" in g:
            g["calc_profit"] = g["calc_profit"] - g["expenses"].fillna(0)
        g.loc[g["revenue"].isna(), "calc_profit"] = np.nan
    elif "profit" in g:
        g["calc_profit"] = g["profit"]
    g["timestamp"] = g.index.to_timestamp()
    return g.reset_index()


def growth_metrics(df: pd.DataFrame) -> Optional[dict]:
    if not (has(df, "revenue") and has(df, "date")):
        return None
    m = monthly_frame(df)
    if len(m) < 2:
        return None
    d_max = df["date"].max()
    last_is_partial = d_max < m["period"].iloc[-1].end_time.normalize()
    use = m.iloc[:-1] if last_is_partial and len(m) >= 3 else m
    cur, prev = use["revenue"].iloc[-1], use["revenue"].iloc[-2]
    if pd.isna(cur) or pd.isna(prev) or prev == 0:
        return None
    note = f"{use['period'].iloc[-1]} vs {use['period'].iloc[-2]}"
    if last_is_partial and len(m) >= 3:
        note += f" (latest month {m['period'].iloc[-1]} excluded: data ends {d_max:%d %b}, so it is incomplete)"
    return {"growth": float((cur - prev) / abs(prev)), "basis": note, "current": float(cur), "previous": float(prev)}


def top_products(df: pd.DataFrame, n: int = 10, by: str = "revenue") -> pd.DataFrame:
    if not has(df, "product") or not has(df, by):
        return pd.DataFrame()
    g = df.groupby("product")[by].sum().sort_values(ascending=False)
    out = g.head(n).reset_index()
    total = g.sum()
    out["share"] = out[by] / total if total else np.nan
    return out


def expense_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    if not (has(df, "expenses") and has(df, "category")):
        return pd.DataFrame()
    g = df.groupby("category")["expenses"].sum().sort_values(ascending=False).reset_index()
    total = g["expenses"].sum()
    g["share"] = g["expenses"] / total if total else np.nan
    return g


def customer_metrics(df: pd.DataFrame, currency: str = "") -> list[Metric]:
    ms: list[Metric] = []
    basis = period_label(df)
    if has(df, "customer"):
        n = int(df["customer"].nunique())
        ms.append(Metric("customers", "Unique customers", n, f"{n:,}", "Count of distinct customers",
                         "How many different customers bought.", basis))
        if has(df, "order_id") or len(df) > 0:
            per = df.groupby("customer")["order_id"].nunique() if has(df, "order_id") else df.groupby("customer").size()
            repeat = float((per > 1).mean())
            ms.append(Metric("repeat_rate", "Repeat customer rate", repeat, pct(repeat),
                             "Customers with 2+ orders ÷ all customers",
                             "Share of customers who came back. Higher usually means better loyalty.", basis,
                             "good" if repeat >= 0.3 else "neutral"))
        if has(df, "revenue"):
            by_c = df.groupby("customer")["revenue"].sum().sort_values(ascending=False)
            if by_c.sum() > 0 and len(by_c) >= 5:
                top_share = float(by_c.head(max(1, int(np.ceil(len(by_c) * 0.1)))).sum() / by_c.sum())
                ms.append(Metric("concentration", "Revenue from top 10% of customers", top_share, pct(top_share),
                                 "Revenue of top 10% customers ÷ total revenue",
                                 "If this is very high, losing a few customers would hurt a lot.", basis,
                                 "bad" if top_share > 0.6 else "neutral"))
    if has(df, "order_id") and has(df, "revenue"):
        orders = df.groupby("order_id")["revenue"].sum()
        if len(orders):
            aov = float(orders.mean())
            ms.append(Metric("aov", "Average order value", aov, money(aov, currency), "Revenue ÷ number of distinct orders",
                             "How much a typical order is worth.", basis))
    return ms


def marketing_metrics(df: pd.DataFrame, currency: str = "") -> list[Metric]:
    ms: list[Metric] = []
    basis = period_label(df)
    spend = _sum(df, "marketing_spend") if has(df, "marketing_spend") else None
    if spend:
        ms.append(Metric("mkt_spend", "Marketing spend", spend, money(spend, currency), "Sum of marketing spend", "", basis))
        if has(df, "revenue"):
            roas = _sum(df, "revenue") / spend
            ms.append(Metric("roas", "Return on ad spend (ROAS)", roas, f"{roas:.2f}x", "Revenue ÷ Marketing spend",
                             "Revenue earned per 1 spent on marketing. Uses all revenue in the data, not only ad-driven sales.",
                             basis, "good" if roas >= 1 else "bad"))
        if has(df, "conversions"):
            conv = _sum(df, "conversions")
            if conv:
                cpa = spend / conv
                ms.append(Metric("cpa", "Cost per conversion", cpa, money(cpa, currency), "Marketing spend ÷ Conversions",
                                 "What it costs, on average, to win one conversion.", basis))
    if has(df, "clicks") and has(df, "impressions") and _sum(df, "impressions"):
        ctr = _sum(df, "clicks") / _sum(df, "impressions")
        ms.append(Metric("ctr", "Click-through rate", ctr, pct(ctr, 2), "Clicks ÷ Impressions",
                         "Share of people who saw an ad and clicked.", basis))
    if has(df, "conversions") and has(df, "clicks") and _sum(df, "clicks"):
        cr = _sum(df, "conversions") / _sum(df, "clicks")
        ms.append(Metric("conv_rate", "Conversion rate", cr, pct(cr, 2), "Conversions ÷ Clicks",
                         "Share of clicks that turned into a sale or lead.", basis))
    return ms


def inventory_metrics(df: pd.DataFrame) -> list[Metric]:
    if not has(df, "stock"):
        return []
    ms: list[Metric] = []
    d = df
    if has(df, "product") and has(df, "date"):
        # Use the latest record per product so repeated snapshots are not double-counted.
        d = df.sort_values("date").dropna(subset=["stock"]).groupby("product", as_index=False).last()
        basis = "Latest stock record per product"
    elif has(df, "product"):
        d = df.dropna(subset=["stock"]).groupby("product", as_index=False).last()
        basis = "Last stock record per product"
    else:
        basis = "All rows (no product column to de-duplicate)"
    total = float(d["stock"].sum())
    ms.append(Metric("stock_total", "Units in stock", total, f"{total:,.0f}", "Sum of stock on hand", "Items currently held.", basis))
    zero = int((d["stock"] <= 0).sum())
    ms.append(Metric("out_of_stock", "Items out of stock", zero, f"{zero:,}", "Count of items with stock ≤ 0",
                     "Items you cannot currently sell.", basis, "bad" if zero else "good"))
    if has(df, "quantity") and has(df, "date") and has(df, "product"):
        months = max(df["date"].dropna().dt.to_period("M").nunique(), 1)
        sold_per_month = float(df["quantity"].sum()) / months
        if sold_per_month > 0:
            cover = total / sold_per_month
            ms.append(Metric("stock_cover", "Stock cover (months)", cover, f"{cover:.1f}", "Units in stock ÷ average units sold per month",
                             "How many months current stock would last at the historical sales pace.",
                             f"{months} month(s) of sales history"))
    return ms


def find_anomalies(m: pd.DataFrame, col: str = "revenue", z: float = 3.0) -> list[dict]:
    """Flag unusual periods with a robust z-score (median/MAD). Needs at least 6 periods."""
    if m.empty or col not in m:
        return []
    s = m[col].dropna()
    if len(s) < 6:
        return []
    med = s.median()
    mad = np.median(np.abs(s - med))
    if mad == 0:
        return []
    rz = 0.6745 * (s - med) / mad
    out = []
    for idx in rz.index[np.abs(rz) > z]:
        out.append({"period": str(m.loc[idx, "period"]), "value": float(s[idx]), "typical": float(med),
                    "direction": "high" if rz[idx] > 0 else "low", "robust_z": float(rz[idx])})
    return out


def recommend_reports(avail: dict[str, bool]) -> list[tuple[str, str]]:
    """Return (report type, reason) pairs ordered by suitability for the available data."""
    recs: list[tuple[str, str]] = []
    if avail["revenue"] or avail["expenses"]:
        recs.append(("Executive Business Report", "A high-level summary works with any revenue or cost data."))
    if avail["revenue"] and avail["expenses"]:
        recs.append(("Financial Performance Report", "Revenue and costs are both present."))
        recs.append(("Profit and Loss Report", "Profit can be calculated from revenue and costs."))
    if avail["revenue"] and (avail["products"] or avail["time"]):
        recs.append(("Sales Analysis Report", "Sales can be broken down by product and/or time."))
    if avail["time"] and avail["revenue"]:
        recs.append(("Business Growth Report", "Several time periods allow growth comparison."))
    if avail["customers"]:
        recs.append(("Customer Analysis Report", "Customer or order identifiers are present."))
    if avail["marketing"]:
        recs.append(("Marketing Performance Report", "Marketing spend or funnel data is present."))
    if avail["inventory"]:
        recs.append(("Inventory Analysis Report", "Stock levels are present."))
    if avail["forecast"]:
        recs.append(("Forecast and Risk Report", "There are 12+ months of revenue history for forecasting."))
    recs.append(("General Data Analysis Report", "Always available: data quality and structure overview."))
    seen, out = set(), []
    for r in recs:
        if r[0] not in seen:
            seen.add(r[0]); out.append(r)
    return out


def driver_analysis(df: pd.DataFrame, by: str = "product") -> Optional[dict]:
    """Which items explain the change in revenue between the last two complete months?"""
    if not (has(df, "revenue") and has(df, "date") and has(df, by)):
        return None
    g = growth_metrics(df)
    if not g:
        return None
    d = df.dropna(subset=["date"]).copy()
    d["period"] = d["date"].dt.to_period("M")
    periods = sorted(d["period"].unique())
    d_max = df["date"].max()
    if d_max < periods[-1].end_time.normalize() and len(periods) >= 3:
        periods = periods[:-1]
    cur, prev = periods[-1], periods[-2]
    piv = d[d["period"].isin([cur, prev])].pivot_table(index=by, columns="period", values="revenue", aggfunc="sum").fillna(0)
    if cur not in piv or prev not in piv:
        return None
    delta = (piv[cur] - piv[prev]).sort_values()
    total = float(delta.sum())
    return {"current": str(cur), "previous": str(prev), "total_change": total,
            "biggest_decline": (str(delta.index[0]), float(delta.iloc[0])) if delta.iloc[0] < 0 else None,
            "biggest_gain": (str(delta.index[-1]), float(delta.iloc[-1])) if delta.iloc[-1] > 0 else None}


def customer_monthly(df: pd.DataFrame) -> pd.DataFrame:
    """Active and first-time customers per month (needs customer + date)."""
    if not (has(df, "customer") and has(df, "date")):
        return pd.DataFrame()
    d = df.dropna(subset=["date", "customer"]).copy()
    if d.empty:
        return pd.DataFrame()
    d["period"] = d["date"].dt.to_period("M")
    first = d.groupby("customer")["period"].min()
    active = d.groupby("period")["customer"].nunique().rename("Active customers")
    new = first.value_counts().rename("New customers")
    out = pd.concat([active, new], axis=1).fillna(0).sort_index()
    out["Returning customers"] = out["Active customers"] - out["New customers"]
    out = out.reset_index().rename(columns={"index": "period"})
    out["timestamp"] = out["period"].dt.to_timestamp()
    return out
