"""Column-role detection, user-correctable mapping, and safe type conversion.

Nothing is invented: values that cannot be parsed become missing (NaN) and are counted in the
cleaning log so the user can see exactly what happened.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

ROLES: dict[str, dict] = {
    "date":            {"label": "Date",              "kind": "date",    "syn": ["date", "order_date", "invoice_date", "transaction_date", "day", "month", "period", "time", "timestamp", "created"]},
    "revenue":         {"label": "Revenue / Sales",   "kind": "money",   "syn": ["revenue", "sales", "total_sales", "income", "turnover", "sale_amount", "amount_sold", "net_sales", "total_revenue", "total"]},
    "expenses":        {"label": "Expenses / Costs",  "kind": "money",   "syn": ["expenses", "expense", "operating_cost", "operating_expenses", "opex", "costs", "cost", "spend_total"]},
    "cogs":            {"label": "Cost of goods sold", "kind": "money",  "syn": ["cogs", "cost_of_goods_sold", "cost_of_sales", "unit_cost_total", "direct_cost"]},
    "profit":          {"label": "Profit (if given)", "kind": "money",   "syn": ["profit", "net_profit", "gross_profit", "net_income", "earnings"]},
    "product":         {"label": "Product / Service", "kind": "text",    "syn": ["product", "product_name", "item", "service", "sku", "item_name", "description"]},
    "category":        {"label": "Category",          "kind": "text",    "syn": ["category", "product_category", "segment", "department", "expense_category", "type", "region", "channel"]},
    "customer":        {"label": "Customer",          "kind": "text",    "syn": ["customer", "customer_id", "customer_name", "client", "buyer", "account"]},
    "order_id":        {"label": "Order / Invoice ID", "kind": "text",   "syn": ["order_id", "order", "invoice", "invoice_id", "invoice_no", "transaction_id", "receipt"]},
    "quantity":        {"label": "Quantity sold",     "kind": "number",  "syn": ["quantity", "qty", "units_sold", "units", "volume", "items_sold"]},
    "stock":           {"label": "Stock on hand",     "kind": "number",  "syn": ["stock", "inventory", "stock_quantity", "on_hand", "stock_level", "units_in_stock"]},
    "marketing_spend": {"label": "Marketing spend",   "kind": "money",   "syn": ["marketing_spend", "ad_spend", "marketing_cost", "campaign_cost", "advertising"]},
    "impressions":     {"label": "Impressions",       "kind": "number",  "syn": ["impressions", "views", "reach"]},
    "clicks":          {"label": "Clicks",            "kind": "number",  "syn": ["clicks", "visits", "sessions"]},
    "conversions":     {"label": "Conversions",       "kind": "number",  "syn": ["conversions", "leads", "signups", "purchases", "orders_count"]},
}
MONEY_ROLES = [r for r, v in ROLES.items() if v["kind"] == "money"]
NUMERIC_ROLES = [r for r, v in ROLES.items() if v["kind"] in ("money", "number")]


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")


def to_numeric_safe(series: pd.Series) -> tuple[pd.Series, int]:
    """Parse numbers like '$1,200.50', '(300)', '12%' or 'Rs 5,000'. Returns (numeric, n_unparseable)."""
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce"), 0
    s = series.astype("string").str.strip()
    neg = s.str.match(r"^\(.*\)$").fillna(False)
    s = s.str.replace(r"[()]", "", regex=True)
    s = s.str.replace(r"(?i)\b(rs|pkr|usd|eur|gbp|inr)\b\.?", "", regex=True)
    s = s.str.replace(r"[\$€£₹¥%\s]", "", regex=True).str.replace(",", "", regex=False)
    out = pd.to_numeric(s, errors="coerce")
    out = out.where(~neg, -out)
    had_value = series.notna() & (series.astype("string").str.strip() != "")
    bad = int((had_value & out.isna()).sum())
    return out.astype(float), bad


def _is_date_like(series: pd.Series) -> float:
    if pd.api.types.is_datetime64_any_dtype(series):
        return 1.0
    sample = series.dropna().astype("string").head(200)
    if sample.empty:
        return 0.0
    # Pure numbers (e.g. 1500) are not dates.
    if pd.to_numeric(sample, errors="coerce").notna().mean() > 0.9:
        return 0.0
    parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
    return float(parsed.notna().mean())


def to_datetime_safe(series: pd.Series) -> tuple[pd.Series, int]:
    if pd.api.types.is_datetime64_any_dtype(series):
        return series, 0
    parsed = pd.to_datetime(series, errors="coerce", format="mixed")
    had = series.notna()
    return parsed, int((had & parsed.isna()).sum())


@dataclass
class Mapping:
    columns: dict[str, str] = field(default_factory=dict)       # role -> source column
    confidence: dict[str, str] = field(default_factory=dict)    # role -> "high" | "medium"

    def get(self, role: str):
        return self.columns.get(role)


def detect_mapping(df: pd.DataFrame) -> Mapping:
    """Suggest a role for each column using names and content. The user can override everything."""
    m = Mapping()
    used: set[str] = set()
    norm_cols = {c: _norm(c) for c in df.columns}
    for role, spec in ROLES.items():
        best, best_score, conf = None, 0, "medium"
        for col, n in norm_cols.items():
            if col in used or n in ("source_file", "sheet"):
                continue
            score = 0
            for rank, syn in enumerate(spec["syn"]):
                if n == syn:
                    score = max(score, 100 - rank)
                elif syn in n.split("_") and len(syn) > 3:
                    score = max(score, 50 - rank)
            if not score:
                continue
            numeric_ratio = to_numeric_safe(df[col])[0].notna().mean()
            if spec["kind"] in ("money", "number") and numeric_ratio < 0.6:
                continue
            if spec["kind"] == "date" and _is_date_like(df[col]) < 0.6:
                continue
            if spec["kind"] == "text" and numeric_ratio > 0.95 and role not in ("customer", "order_id", "product"):
                continue
            if score > best_score:
                best, best_score = col, score
                conf = "high" if score >= 90 else "medium"
        if best is not None:
            m.columns[role] = best
            m.confidence[role] = conf
            used.add(best)
    # A generic "total"/"type"/"region" match is weak; keep but flag as medium.
    return m


@dataclass
class Standardized:
    df: pd.DataFrame                  # columns renamed to role names (+ all unmapped columns untouched)
    mapping: Mapping
    log: list[str]                    # human-readable cleaning notes
    unparseable: dict[str, int]       # role -> count of values turned into missing


def apply_mapping(df: pd.DataFrame, mapping: Mapping) -> Standardized:
    out = pd.DataFrame(index=df.index)
    log: list[str] = []
    bad: dict[str, int] = {}
    mapped_src = set(mapping.columns.values())
    for role, col in mapping.columns.items():
        if col not in df.columns:
            continue
        kind = ROLES[role]["kind"]
        if kind == "date":
            out[role], n = to_datetime_safe(df[col])
        elif kind in ("money", "number"):
            out[role], n = to_numeric_safe(df[col])
        else:
            out[role], n = df[col].astype("string").str.strip(), 0
        if n:
            bad[role] = n
            log.append(f"{n:,} value(s) in '{col}' could not be read as {ROLES[role]['label'].lower()} and were left blank (not guessed).")
    for col in df.columns:
        if col not in mapped_src:
            out[f"other::{col}"] = df[col]
    return Standardized(out, mapping, log, bad)


@dataclass
class Quality:
    rows: int
    columns: int
    missing_cells: int
    missing_pct: float
    duplicate_rows: int
    issues: list[str]
    per_column: pd.DataFrame
    score: int   # 0-100 simple completeness/consistency score; see README for definition


def assess_quality(df: pd.DataFrame, std: Standardized | None = None) -> Quality:
    rows, cols = len(df), df.shape[1]
    miss = int(df.isna().sum().sum())
    total = max(rows * cols, 1)
    dup = int(df.duplicated().sum()) if rows else 0
    issues: list[str] = []
    if rows == 0:
        issues.append("No data rows were loaded.")
    if rows and rows < 10:
        issues.append("Very few rows: results are descriptive only and may be unstable.")
    if miss:
        issues.append(f"{miss:,} blank cells ({miss/total:.1%} of all cells).")
    if dup:
        issues.append(f"{dup:,} exact duplicate rows (not removed automatically).")
    if std is not None:
        issues.extend(std.log)
        for role in MONEY_ROLES:
            if role in std.df and std.df[role].dropna().lt(0).any() and role in ("revenue", "expenses", "quantity"):
                n = int((std.df[role] < 0).sum())
                issues.append(f"{n:,} negative value(s) in {ROLES[role]['label'].lower()} — check for refunds or entry errors.")
        if "date" in std.df:
            d = std.df["date"].dropna()
            if len(d) and d.max() > pd.Timestamp.now() + pd.Timedelta(days=366):
                issues.append("Some dates are more than a year in the future — check the date format (day/month vs month/day).")
    per = pd.DataFrame({
        "column": df.columns.astype(str),
        "type": [str(t) for t in df.dtypes],
        "missing": [int(df[c].isna().sum()) for c in df.columns],
        "missing %": [round(df[c].isna().mean() * 100, 1) if rows else 0 for c in df.columns],
        "unique": [int(df[c].nunique(dropna=True)) for c in df.columns],
    })
    penalty = min(40, 100 * miss / total * 1.5) + min(20, 100 * dup / max(rows, 1)) + min(30, 3 * sum(std.unparseable.values()) if std else 0)
    score = int(max(0, round(100 - penalty)))
    return Quality(rows, cols, miss, miss / total, dup, issues, per, score)
