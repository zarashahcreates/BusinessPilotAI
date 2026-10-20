from __future__ import annotations

import numpy as np
import pandas as pd


def sample_catalog() -> dict[str, str]:
    return {
        "Retail sales": "120 days of store transactions with products, regions, costs, and payment status.",
        "Inventory snapshot": "SKU-level stock, reorder points, and recent movement.",
        "Service invoices": "Professional-services billing with clients and collection status.",
    }


def load_sample(name: str) -> pd.DataFrame:
    if name == "Inventory snapshot":
        return _inventory_snapshot()
    if name == "Service invoices":
        return _service_invoices()
    return _retail_sales()


def _retail_sales() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    start = pd.Timestamp("2026-06-01")
    dates = pd.date_range(start, periods=120, freq="D")
    products = [
        ("Atlas kettle", 4200, 2600),
        ("Harbor blender", 8900, 5400),
        ("Cedar lamp", 3100, 1700),
        ("Nimbus fan", 6500, 4100),
        ("Lumen bulb pack", 900, 420),
        ("Forge pan", 4800, 2900),
    ]
    regions = ["Karachi", "Lahore", "Islamabad", "Faisalabad"]
    rows = []
    for day in dates:
        weekday = day.dayofweek
        season = 1.15 if day.month in (7, 8, 12) else 1.0
        n_tx = int(rng.integers(8, 18) + (3 if weekday >= 5 else 0))
        for _ in range(n_tx):
            product, price, cost = products[int(rng.integers(0, len(products)))]
            region = regions[int(rng.integers(0, len(regions)))]
            qty = int(rng.integers(1, 6))
            if weekday >= 5:
                qty += int(rng.integers(0, 3))
            revenue = round(price * qty * season * float(rng.uniform(0.95, 1.05)), 2)
            expenses = round(cost * qty * float(rng.uniform(0.97, 1.08)), 2)
            overdue_chance = 0.18 if region in {"Karachi", "Faisalabad"} else 0.08
            status = "Overdue" if rng.random() < overdue_chance else "Paid"
            rows.append(
                {
                    "date": day.date().isoformat(),
                    "product": product,
                    "region": region,
                    "customer": f"C-{int(rng.integers(1000, 1400))}",
                    "quantity": qty,
                    "revenue": revenue,
                    "expenses": expenses,
                    "payment_status": status,
                }
            )
    return pd.DataFrame(rows)


def _inventory_snapshot() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    skus = [
        ("ATL-KTL", "Atlas kettle", "Small appliances"),
        ("HRB-BLD", "Harbor blender", "Small appliances"),
        ("CDR-LMP", "Cedar lamp", "Home"),
        ("NMB-FAN", "Nimbus fan", "Climate"),
        ("LMN-BLB", "Lumen bulb pack", "Consumables"),
        ("FRG-PAN", "Forge pan", "Kitchen"),
        ("SLK-MUG", "Silk mug set", "Kitchen"),
        ("ORB-SPK", "Orbit speaker", "Electronics"),
    ]
    rows = []
    for sku, name, category in skus:
        on_hand = int(rng.integers(12, 220))
        reorder = int(rng.integers(20, 60))
        incoming = int(rng.integers(0, 40))
        sold_30 = int(rng.integers(8, 90))
        unit_cost = int(rng.choice([420, 900, 1700, 2600, 2900, 4100, 5400]))
        rows.append(
            {
                "sku": sku,
                "product": name,
                "category": category,
                "stock": on_hand,
                "reorder_point": reorder,
                "incoming": incoming,
                "units_sold_30d": sold_30,
                "unit_cost": unit_cost,
                "stock_value": on_hand * unit_cost,
                "days_of_cover": round(on_hand / max(sold_30 / 30, 0.1), 1),
            }
        )
    return pd.DataFrame(rows)


def _service_invoices() -> pd.DataFrame:
    rng = np.random.default_rng(21)
    start = pd.Timestamp("2026-01-06")
    dates = pd.date_range(start, periods=40, freq="W-MON")
    clients = ["Helix Labs", "North Gate", "Pinnacle Foods", "River Clinic", "Oak & Co", "Brightline"]
    services = ["Retainer", "Implementation", "Audit", "Training", "Support block"]
    rows = []
    invoice_id = 2400
    for day in dates:
        for _ in range(int(rng.integers(2, 5))):
            invoice_id += 1
            amount = float(rng.choice([45000, 72000, 98000, 125000, 180000, 240000]))
            cost = round(amount * float(rng.uniform(0.42, 0.68)), 2)
            status = str(rng.choice(["Paid", "Paid", "Paid", "Overdue", "Open"], p=[0.45, 0.2, 0.1, 0.15, 0.1]))
            rows.append(
                {
                    "invoice_date": day.date().isoformat(),
                    "invoice_id": f"INV-{invoice_id}",
                    "client": clients[int(rng.integers(0, len(clients)))],
                    "service": services[int(rng.integers(0, len(services)))],
                    "region": str(rng.choice(["Karachi", "Lahore", "Remote"])),
                    "income": amount,
                    "costs": cost,
                    "status": status,
                }
            )
    return pd.DataFrame(rows)
