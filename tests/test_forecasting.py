import unittest
from tests import helpers
import numpy as np
import pandas as pd
from businesspilot import forecasting as F


class Forecasting(unittest.TestCase):
    def test_available_with_enough_history(self):
        r = F.forecast_series(helpers.monthly_history(36), "revenue", 6)
        self.assertTrue(r.available)
        self.assertEqual(len(r.forecast), 6)
        self.assertTrue((r.forecast["lower"] <= r.forecast["point"]).all() and (r.forecast["point"] <= r.forecast["upper"]).all())
        self.assertGreater(r.metrics["backtest_points"], 5)
        self.assertTrue(r.limitations and r.assumptions)

    def test_interval_widens_with_horizon(self):
        r = F.forecast_series(helpers.monthly_history(36), "revenue", 6)
        w = (r.forecast["upper"] - r.forecast["lower"]).to_numpy()
        self.assertTrue(w[-1] > w[0])

    def test_seasonal_data_picks_seasonal_model(self):
        r = F.forecast_series(helpers.monthly_history(36, seasonal=True), "revenue", 6)
        self.assertIn("Seasonal", r.model)

    def test_insufficient_history_explains_need(self):
        r = F.forecast_series(helpers.monthly_history(8), "revenue", 6)
        self.assertFalse(r.available)
        self.assertIn("at least 12", r.reason); self.assertTrue(r.forecast.empty)

    def test_constant_series_unavailable(self):
        m = helpers.monthly_history(24); m["revenue"] = 100.0
        self.assertFalse(F.forecast_series(m, "revenue").available)

    def test_too_many_gaps_unavailable_few_gaps_disclosed(self):
        m = helpers.monthly_history(36)
        m.loc[[10, 11, 12, 13, 14, 15, 16], "revenue"] = np.nan
        self.assertFalse(F.forecast_series(m, "revenue").available)
        m = helpers.monthly_history(36); m.loc[10, "revenue"] = np.nan
        r = F.forecast_series(m, "revenue")
        self.assertTrue(r.available); self.assertTrue(r.history["interpolated"].sum() == 1)
        self.assertTrue(any("interpolation" in a for a in r.assumptions))

    def test_partial_last_month_excluded(self):
        m = helpers.monthly_history(24)
        r = F.forecast_series(m, "revenue", source_end=m["timestamp"].iloc[-1] + pd.Timedelta(days=9))
        self.assertEqual(len(r.history), 23)

    def test_no_look_ahead_leakage_in_backtest(self):
        """Changing FUTURE values must never change a prediction made earlier."""
        y = helpers.monthly_history(30)["revenue"].to_numpy()
        for name, (fn, need, _) in F.MODELS.items():
            if len(y) < need + 3:
                continue
            p1, _, idx = F._backtest(y, fn, 15)
            y2 = y.copy(); y2[-4:] *= 5
            p2, _, _ = F._backtest(y2, fn, 15)
            k = len([i for i in idx if i < len(y) - 4])
            np.testing.assert_allclose(p1[:k], p2[:k], err_msg=name)

    def test_horizon_clamped_and_non_negative(self):
        m = helpers.monthly_history(24); m["revenue"] = np.linspace(500, 20, 24) + np.random.default_rng(0).normal(0, 5, 24)
        r = F.forecast_series(m, "revenue", 99)
        self.assertEqual(len(r.forecast), F.MAX_HORIZON)
        self.assertTrue((r.forecast[["point", "lower", "upper"]] >= 0).all().all())

    def test_scenario_is_pure_scaling(self):
        r = F.forecast_series(helpers.monthly_history(36), "revenue", 3)
        s = F.apply_scenario(r.forecast, 10)
        np.testing.assert_allclose(s["point"], r.forecast["point"] * 1.1)

    def test_baseline_comparison_reported_honestly(self):
        r = F.forecast_series(helpers.monthly_history(36, seasonal=False), "revenue", 3)
        self.assertIn("beats_baseline", r.metrics)
        self.assertIn("Naive (repeat last period)", r.comparison["Model"].tolist())

    def test_risk_indicators_are_not_probabilities(self):
        m = helpers.monthly_history(24); m["expenses"] = m["revenue"] * 0.8; m["calc_profit"] = m["revenue"] * 0.2
        ind = F.risk_indicators(m)
        self.assertTrue(ind)
        for i in ind:
            self.assertIn(i["level"], ("Low", "Medium", "High")); self.assertNotIn("%  probability", i["detail"])


class ProbabilityModel(unittest.TestCase):
    def _df(self, n=120):
        rng = np.random.default_rng(0)
        df = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=n), "amount": rng.normal(100, 20, n), "term": rng.integers(7, 60, n)})
        df["overdue"] = np.where(df.amount + rng.normal(0, 15, n) > 105, "yes", "no")
        return df

    def test_chronological_split_and_baseline(self):
        from businesspilot.prediction import train_probability_model
        r = train_probability_model(self._df(), "overdue", "date")
        self.assertIn("Chronological", r["evaluation"]); self.assertIn("baseline_brier", r)
        self.assertEqual(r["n_train"] + r["n_test"], 120)
        self.assertTrue(np.allclose(r["predictions"].filter(like="probability_").sum(axis=1), 1.0))

    def test_refuses_small_or_single_class(self):
        from businesspilot.prediction import train_probability_model
        with self.assertRaises(ValueError):
            train_probability_model(self._df(20), "overdue")
        df = self._df(); df["overdue"] = "no"
        with self.assertRaises(ValueError):
            train_probability_model(df, "overdue")


if __name__ == "__main__":
    unittest.main()
