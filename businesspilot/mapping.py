from __future__ import annotations

from typing import Any

import pandas as pd

ROLE_ALIASES: dict[str, list[str]] = {
    "date": ["date", "order_date", "invoice_date", "day", "period", "transaction_date", "created_at"],
    "revenue": ["revenue", "sales", "total_sales", "income", "amount", "turnover", "net_sales"],
    "expense": ["expense", "expenses", "cost", "costs", "cogs", "spend"],
    "profit": ["profit", "net_profit", "gross_profit", "margin_amount"],
    "quantity": ["quantity", "units_sold", "units", "qty", "volume"],
    "stock": ["stock", "inventory", "stock_quantity", "on_hand"],
    "product": ["product", "item", "sku", "item_name", "product_name", "service"],
    "region": ["region", "city", "location", "market", "branch", "store"],
    "customer": ["customer", "client", "account", "customer_name"],
    "status": ["status", "payment_status", "order_status", "overdue"],
}

ROLE_LABELS = {
    "date": "Date",
    "revenue": "Revenue",
    "expense": "Expense",
    "profit": "Profit",
    "quantity": "Quantity",
    "stock": "Stock",
    "product": "Product / item",
    "region": "Region / location",
    "customer": "Customer",
    "status": "Status / outcome",
}

ROLE_HELP = {
    "date": "Used for trends, period filters, and forecasts.",
    "revenue": "Primary income metric.",
    "expense": "Cost metric used with revenue to estimate profit.",
    "profit": "Use if profit is already present as a column.",
    "quantity": "Units sold or handled.",
    "stock": "Inventory on hand.",
    "product": "Category used for mix and ranking charts.",
    "region": "Optional geography split.",
    "customer": "Optional customer analysis.",
    "status": "Historical outcome for the probability model.",
}


def infer_column_roles(df: pd.DataFrame) -> dict[str, str | None]:
    roles: dict[str, str | None] = {role: None for role in ROLE_ALIASES}
    used: set[str] = set()
    lower_lookup = {str(col).strip().lower(): col for col in df.columns}

    for role, aliases in ROLE_ALIASES.items():
        for alias in aliases:
            if alias in lower_lookup and lower_lookup[alias] not in used:
                roles[role] = str(lower_lookup[alias])
                used.add(lower_lookup[alias])
                break
        if roles[role] is None:
            for col in df.columns:
                name = str(col).strip().lower()
                if col in used or name.startswith("__"):
                    continue
                if any(alias in name for alias in aliases):
                    roles[role] = str(col)
                    used.add(col)
                    break
    return roles


def sanitize_roles(df: pd.DataFrame, roles: dict[str, Any] | None) -> dict[str, str | None]:
    columns = {str(c) for c in df.columns}
    cleaned = infer_column_roles(df) if not roles else dict(roles)
    for role in ROLE_ALIASES:
        value = cleaned.get(role)
        if value in (None, "", "— not mapped —"):
            cleaned[role] = None
        elif str(value) not in columns:
            cleaned[role] = None
        else:
            cleaned[role] = str(value)
    return cleaned


def resolve_report_type(df: pd.DataFrame, selected: str, roles: dict[str, str | None] | None = None) -> str:
    if selected != "Auto-detect":
        return selected
    roles = sanitize_roles(df, roles)
    if roles.get("stock") and not roles.get("revenue"):
        return "Inventory"
    if roles.get("revenue") or roles.get("product"):
        return "Sales performance"
    if roles.get("expense") or roles.get("profit"):
        return "Financial performance"
    if roles.get("customer") and roles.get("status"):
        return "Customer analysis"
    cols_lower = {str(c).lower() for c in df.columns}
    if any(any(k in c for k in ["stock", "inventory", "sku"]) for c in cols_lower):
        return "Inventory"
    if any(any(k in c for k in ["sale", "revenue", "product", "order"]) for c in cols_lower):
        return "Sales performance"
    if any(any(k in c for k in ["expense", "cost", "profit", "income"]) for c in cols_lower):
        return "Financial performance"
    return "General business report"
