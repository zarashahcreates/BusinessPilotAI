import unittest
from tests import helpers
import numpy as np
import pandas as pd
from businesspilot import metrics as M
from businesspilot.schema import Mapping, apply_mapping, assess_quality, detect_mapping, to_numeric_safe


def metric(bundle, key):
    return next((m for m in bundle.metrics if m.key == key), None)


class Parsing(unittest.TestCase):
    def test_currency_formats(self):
        s, bad = to_numeric_safe(pd.Series(["$1,200.50", "(300)", "12%", "Rs 5,000", "abc", None, ""]))
        self.assertEqual(s.iloc[:4].tolist(), [1200.5, -300.0, 12.0, 5000.0])
        self.assertTrue(np.isnan(s.iloc[4])); self.assertEqual(bad, 1)

    def test_unparseable_values_are_blank_not_zero(self):
        df = pd.DataFrame({"Date": pd.date_range("2025-01-01", periods=5).astype(str), "Sales": ["10", "oops", "30", "40", "50"]})
        std = apply_mapping(df, detect_mapping(df))
        self.assertTrue(np.isnan(std.df["revenue"].iloc[1]))
        self.assertEqual(std.unparseable["revenue"], 1)
        self.assertTrue(any("not guessed" in n for n in std.log))


class Detection(unittest.TestCase):
    def test_detects_common_columns(self):
        m = detect_mapping(helpers.small_sales()).columns
        self.assertEqual(m, {"date": "Date", "revenue": "Sales", "expenses": "Expenses", "product": "Product", "quantity": "Quantity"})

    def test_does_not_assume_financial_data(self):
        df = pd.DataFrame({"name": ["a", "b", "c"], "notes": ["x", "y", "z"], "score": [1, 2, 3]})
        self.assertNotIn("revenue", detect_mapping(df).columns)

    def test_numeric_column_not_taken_as_date(self):
        df = pd.DataFrame({"period": [1500, 1600, 1700], "sales": [1, 2, 3]})
        self.assertNotIn("date", detect_mapping(df).columns)


class Calculations(unittest.TestCase):
    def setUp(self):
        self.b = helpers.bundle_for(helpers.small_sales(), "")

    def test_totals_profit_margin(self):
        self.assertAlmostEqual(metric(self.b, "revenue").value, 1200.0)
        self.assertAlmostEqual(metric(self.b, "expenses").value, 450.0)
        self.assertAlmostEqual(metric(self.b, "net_profit").value, 750.0)
        self.assertAlmostEqual(metric(self.b, "margin").value, 750 / 1200)
        self.assertAlmostEqual(metric(self.b, "quantity").value, 11.0)

    def test_growth_excludes_incomplete_last_month(self):
        # Data ends 31 Mar (complete): Mar 400 vs Feb 500 -> -20%.
        self.assertAlmostEqual(metric(self.b, "growth").value, (400 - 500) / 500)

    def test_growth_skips_partial_month(self):
        df = helpers.small_sales(); df.loc[5, "Date"] = "2025-03-10"   # March now ends on the 10th
        b = helpers.bundle_for(df, "")
        # Mar is partial -> compare Feb (500) with Jan (300) = +66.7%
        self.assertAlmostEqual(metric(b, "growth").value, (500 - 300) / 300)
        self.assertIn("incomplete", metric(b, "growth").basis)

    def test_monthly_aggregation(self):
        m = self.b.monthly
        self.assertEqual(m["revenue"].tolist(), [300.0, 500.0, 400.0])
        self.assertEqual(m["calc_profit"].tolist(), [200.0, 300.0, 250.0])

    def test_top_products(self):
        t = self.b.products
        self.assertEqual(t.iloc[0]["product"], "A"); self.assertAlmostEqual(t.iloc[0]["share"], 650 / 1200)
        self.assertAlmostEqual(t["share"].sum(), 1.0)

    def test_gross_vs_net_with_cogs(self):
        df = pd.DataFrame({"Date": ["2025-01-01"] * 2, "Sales": [1000, 500], "COGS": [400, 200], "Expenses": [100, 50]})
        b = helpers.bundle_for(df, "")
        self.assertAlmostEqual(metric(b, "gross_profit").value, 900.0)
        self.assertAlmostEqual(metric(b, "net_profit").value, 750.0)

    def test_profit_column_used_when_no_costs(self):
        df = pd.DataFrame({"Date": ["2025-01-01", "2025-01-02"], "Sales": [100, 100], "Profit": [30, 20]})
        b = helpers.bundle_for(df, "")
        self.assertAlmostEqual(metric(b, "net_profit").value, 50.0)
        self.assertEqual(M.profit_components(b.data)["source"], "reported")

    def test_no_invented_metrics_without_inputs(self):
        df = pd.DataFrame({"Date": ["2025-01-01", "2025-02-01"], "Sales": [100, 200]})
        b = helpers.bundle_for(df, "")
        self.assertIsNone(metric(b, "net_profit")); self.assertIsNone(metric(b, "margin")); self.assertIsNone(metric(b, "expenses"))

    def test_missing_revenue_values_are_excluded_not_zeroed(self):
        df = pd.DataFrame({"Date": ["2025-01-01", "2025-01-02", "2025-01-03"], "Sales": [100, None, 300], "Expenses": [10, 20, 30]})
        b = helpers.bundle_for(df, "")
        self.assertAlmostEqual(metric(b, "revenue").value, 400.0)
        self.assertTrue(any("blank" in i for i in b.quality.issues))

    def test_empty_dataset(self):
        df = pd.DataFrame({"Date": pd.Series(dtype="str"), "Sales": pd.Series(dtype="float")})
        b = helpers.bundle_for(df, "")
        self.assertEqual(b.metrics, [])

    def test_filters(self):
        from businesspilot.pipeline import run_analysis
        df = helpers.small_sales()
        b = run_analysis(df, detect_mapping(df), "", date_range=("2025-02-01", "2025-03-31"), category_filters={"product": ["A"]})
        self.assertAlmostEqual(metric(b, "revenue").value, 550.0)
        self.assertIn("Filters applied", b.filters_note)

    def test_customer_and_marketing_metrics(self):
        df = pd.DataFrame({"Date": pd.date_range("2025-01-01", periods=6), "Customer": ["a", "a", "b", "c", "c", "c"],
                           "Order ID": list("123456"), "Sales": [10] * 6, "Marketing Spend": [5] * 6, "Clicks": [10] * 6, "Impressions": [100] * 6,
                           "Conversions": [2] * 6})
        b = helpers.bundle_for(df, "")
        self.assertEqual(metric(b, "customers").value, 3)
        self.assertAlmostEqual(metric(b, "repeat_rate").value, 2 / 3)
        self.assertAlmostEqual(metric(b, "roas").value, 60 / 30)
        self.assertAlmostEqual(metric(b, "ctr").value, 0.1)
        self.assertAlmostEqual(metric(b, "cpa").value, 30 / 12)

    def test_inventory_uses_latest_record_per_product(self):
        df = pd.DataFrame({"Date": ["2025-01-01", "2025-02-01", "2025-01-01", "2025-02-01"], "Product": ["A", "A", "B", "B"], "Stock": [10, 4, 5, 0]})
        b = helpers.bundle_for(df, "")
        self.assertEqual(metric(b, "stock_total").value, 4.0)
        self.assertEqual(metric(b, "out_of_stock").value, 1)

    def test_anomaly_detection(self):
        m = pd.DataFrame({"period": [str(i) for i in range(12)], "revenue": [100, 102, 98, 101, 99, 100, 500, 101, 99, 100, 102, 98]})
        a = M.find_anomalies(m)
        self.assertEqual([x["period"] for x in a], ["6"]); self.assertEqual(a[0]["direction"], "high")
        self.assertEqual(M.find_anomalies(m.head(4)), [])   # too little data -> no claims

    def test_recommend_reports_depends_on_data(self):
        full = M.available_analyses(helpers.bundle_for(helpers.daily_orders(), "").data)
        names = [n for n, _ in M.recommend_reports(full)]
        self.assertIn("Forecast and Risk Report", names); self.assertIn("Customer Analysis Report", names)
        names2 = [n for n, _ in M.recommend_reports({k: False for k in full})]
        self.assertEqual(names2, ["General Data Analysis Report"])


class Quality(unittest.TestCase):
    def test_duplicates_missing_negative(self):
        df = pd.DataFrame({"Date": ["2025-01-01"] * 3, "Sales": [10, 10, -5], "Expenses": [1, 1, None]})
        q = assess_quality(df, apply_mapping(df, detect_mapping(df)))
        self.assertEqual(q.duplicate_rows, 1); self.assertEqual(q.missing_cells, 1)
        self.assertTrue(any("negative" in i for i in q.issues))
        self.assertLess(q.score, 100)


if __name__ == "__main__":
    unittest.main()
