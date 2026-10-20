import pandas as pd
import numpy as np

def profile_data(df: pd.DataFrame) -> dict:
    warnings = []
    if df.empty:
        warnings.append("No data rows were loaded.")
    if df.columns.duplicated().any():
        warnings.append("Duplicate column names detected. Rename columns before relying on the analysis.")
    missing = int(df.isna().sum().sum())
    if missing:
        warnings.append(f"{missing} missing cells detected. Check whether missing values affect calculations.")
    duplicates = int(df.duplicated().sum())
    if duplicates:
        warnings.append(f"{duplicates} duplicate rows detected. They have not been automatically deleted.")
    if len(df) < 10:
        warnings.append("Small dataset: findings may be unstable and should be treated as descriptive.")
    return {
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "duplicate_rows": duplicates,
        "missing_cells": missing,
        "column_types": {str(c): str(t) for c, t in df.dtypes.items()},
        "warnings": warnings,
    }

def _numeric_columns(df):
    out = []
    for col in df.columns:
        numeric = pd.to_numeric(df[col], errors="coerce")
        if numeric.notna().sum() >= 2:
            out.append((col, numeric))
    return out

def detect_numeric_insights(df: pd.DataFrame, currency="Rs") -> dict:
    numeric_cols = _numeric_columns(df)
    insights = {}
    lower_map = {str(c).lower(): c for c in df.columns}
    # Prefer recognizable business columns for understandable KPIs.
    preferred = [
        (["revenue", "sales", "total_sales", "income"], "Revenue"),
        (["expense", "expenses", "cost", "costs"], "Expenses"),
        (["profit", "net_profit", "gross_profit"], "Profit"),
        (["quantity", "units_sold", "units"], "Quantity"),
        (["stock", "inventory", "stock_quantity"], "Stock"),
    ]
    used = set()
    for keys, label in preferred:
        for col in df.columns:
            c = str(col).lower().strip()
            if c in keys and col not in used:
                values = pd.to_numeric(df[col], errors="coerce").dropna()
                if not values.empty:
                    insights[f"{label} total"] = f"{currency} {values.sum():,.2f}" if label in ["Revenue", "Expenses", "Profit"] else f"{values.sum():,.2f}"
                    used.add(col)
                    break
    revenue_col = next((c for c in df.columns if str(c).lower().strip() in ["revenue", "sales", "total_sales", "income"]), None)
    expense_col = next((c for c in df.columns if str(c).lower().strip() in ["expense", "expenses", "cost", "costs"]), None)
    if revenue_col and expense_col:
        rev = pd.to_numeric(df[revenue_col], errors="coerce").sum()
        exp = pd.to_numeric(df[expense_col], errors="coerce").sum()
        if rev:
            insights["Calculated profit (revenue − expenses)"] = f"{currency} {rev-exp:,.2f}"
            insights["Calculated margin"] = f"{(rev-exp)/rev*100:.1f}%"
    for col, vals in numeric_cols:
        if col in used or str(col).startswith("__"):
            continue
        if len(insights) >= 8:
            break
        insights[f"{col} total"] = f"{vals.sum():,.2f}"
    return insights

def build_chart_data(df: pd.DataFrame):
    if df.empty:
        return None, None, None
    numeric_cols = [c for c in df.columns if pd.to_numeric(df[c], errors="coerce").notna().sum() >= 2 and not str(c).startswith("__")]
    if not numeric_cols:
        return None, None, None
    date_cols = []
    cat_cols = []
    for c in df.columns:
        if c in numeric_cols or str(c).startswith("__"):
            continue
        parsed = pd.to_datetime(df[c], errors="coerce")
        if parsed.notna().sum() >= max(2, int(0.6 * len(df))):
            date_cols.append(c)
        elif df[c].nunique(dropna=True) <= 30:
            cat_cols.append(c)
    x_col = date_cols[0] if date_cols else (cat_cols[0] if cat_cols else None)
    y_col = numeric_cols[0]
    if x_col is None:
        return None, None, None
    work = df[[x_col, y_col]].copy()
    work[y_col] = pd.to_numeric(work[y_col], errors="coerce")
    work = work.dropna()
    if not work.empty and x_col in date_cols:
        work[x_col] = pd.to_datetime(work[x_col], errors="coerce")
        work = work.groupby(x_col, as_index=False)[y_col].sum().sort_values(x_col)
    elif not work.empty and work[x_col].nunique() > 20:
        work = work.head(20)
    return (work, x_col, y_col) if not work.empty else (None, None, None)
