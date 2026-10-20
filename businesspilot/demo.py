"""Synthetic demonstration data. NOT real business results — used for the demo button and tests."""
from __future__ import annotations

import numpy as np
import pandas as pd


def make_demo_data(seed: int = 7, start: str = "2024-01-01", months: int = 30) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    products = {"Classic Coffee Beans": (18, 9), "Espresso Machine": (260, 170), "Ceramic Mug": (9, 4),
                "Tea Sampler": (22, 11), "Grinder": (75, 45), "Gift Box": (40, 22)}
    costs = ["Rent", "Salaries", "Marketing", "Utilities", "Shipping", "Software"]
    customers = [f"CUST-{i:03d}" for i in range(1, 121)]
    rows, oid = [], 1000
    days = pd.date_range(start, periods=months * 30, freq="D")
    for d in days:
        m = (d.year - days[0].year) * 12 + d.month - days[0].month
        season = 1 + 0.25 * np.sin((d.month - 3) / 12 * 2 * np.pi)
        trend = 1 + 0.015 * m
        n = rng.poisson(3.2 * season * trend)
        for _ in range(n):
            p = rng.choice(list(products), p=[.34, .06, .22, .14, .1, .14])
            price, unit_cost = products[p]
            q = int(rng.integers(1, 4))
            oid += 1
            promo = 1.6 if (d.year == days[0].year + 1 and d.month == 11) else 1.0
            rows.append({"Date": d.date().isoformat(), "Order ID": f"ORD-{oid}", "Customer": customers[int(rng.integers(0, len(customers)))],
                         "Product": p, "Quantity": q, "Revenue": round(price * q * promo * rng.uniform(.95, 1.05), 2),
                         "Expenses": round(unit_cost * q * rng.uniform(.95, 1.05), 2), "Expense Category": "Cost of stock"})
    df = pd.DataFrame(rows)
    overhead = []
    for per in pd.period_range(days[0], days[-1], freq="M"):
        for c, base in zip(costs, [1800, 5200, 900, 350, 600, 180]):
            overhead.append({"Date": per.to_timestamp().date().isoformat(), "Order ID": None, "Customer": None, "Product": None, "Quantity": None,
                             "Revenue": None, "Expenses": round(base * rng.uniform(.95, 1.08), 2), "Expense Category": c})
    out = pd.concat([df, pd.DataFrame(overhead)], ignore_index=True).sort_values("Date").reset_index(drop=True)
    return out
