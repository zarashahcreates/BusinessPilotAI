"""Transparent time-series forecasting with honest validation.

Candidate models (all simple, all explainable): naive, 3-period average, linear trend,
damped Holt linear trend, and seasonal naive (only with >= 24 periods). The model is chosen with
*rolling-origin* back-testing: every forecast is made using only data that came before it, so
there is no look-ahead leakage. Intervals are empirical prediction intervals from those
out-of-sample errors. They are NOT event probabilities.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product
from typing import Callable, Optional

import numpy as np
import pandas as pd

MIN_PERIODS = 12
MAX_HORIZON = 12


@dataclass
class ForecastResult:
    available: bool
    reason: str = ""
    target: str = "revenue"
    history: pd.DataFrame = field(default_factory=pd.DataFrame)     # timestamp, value, interpolated
    forecast: pd.DataFrame = field(default_factory=pd.DataFrame)    # timestamp, point, lower, upper
    backtest: pd.DataFrame = field(default_factory=pd.DataFrame)    # timestamp, actual, predicted
    model: str = ""
    model_description: str = ""
    metrics: dict = field(default_factory=dict)
    comparison: pd.DataFrame = field(default_factory=pd.DataFrame)  # model, MAE, RMSE, MAPE
    assumptions: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    interval_level: float = 0.8


# ---------------------------------------------------------------- model implementations
def _naive(y: np.ndarray, h: int) -> np.ndarray:
    return np.repeat(y[-1], h)


def _mean3(y: np.ndarray, h: int) -> np.ndarray:
    return np.repeat(y[-3:].mean(), h)


def _linear(y: np.ndarray, h: int) -> np.ndarray:
    n = len(y)
    x = np.arange(n)
    slope, intercept = np.polyfit(x, y, 1)
    return intercept + slope * np.arange(n, n + h)


def _holt_fit(y: np.ndarray, alpha: float, beta: float, phi: float):
    level, trend = y[0], y[1] - y[0]
    sse = 0.0
    for t in range(1, len(y)):
        pred = level + phi * trend
        sse += (y[t] - pred) ** 2
        new_level = alpha * y[t] + (1 - alpha) * (level + phi * trend)
        trend = beta * (new_level - level) + (1 - beta) * phi * trend
        level = new_level
    return level, trend, sse


def _holt(y: np.ndarray, h: int) -> np.ndarray:
    best = None
    for a, b in product((0.2, 0.4, 0.6, 0.8), (0.1, 0.3, 0.5)):
        level, trend, sse = _holt_fit(y, a, b, 0.9)
        if best is None or sse < best[0]:
            best = (sse, level, trend)
    _, level, trend = best
    phi = 0.9
    steps = np.cumsum([phi ** k for k in range(1, h + 1)])
    return level + steps * trend


def _seasonal_naive(y: np.ndarray, h: int, m: int = 12) -> np.ndarray:
    return np.array([y[len(y) - m + (k % m)] for k in range(h)])


def _seasonal_drift(y: np.ndarray, h: int, m: int = 12) -> np.ndarray:
    shift = y[-m:].mean() - y[-2 * m:-m].mean()          # year-over-year level change
    return np.array([y[len(y) - m + (k % m)] + shift * (1 + k // m) for k in range(h)])


MODELS: dict[str, tuple[Callable, int, str]] = {
    "Naive (repeat last period)": (_naive, 2, "Assumes next period equals the latest one. The baseline every other model must beat."),
    "3-period average": (_mean3, 3, "Assumes next period equals the average of the last three."),
    "Linear trend": (_linear, 6, "Fits a straight line through history and extends it."),
    "Damped Holt trend": (_holt, 6, "Exponential smoothing with a trend that gradually flattens, so growth is not extrapolated forever."),
    "Seasonal naive (12 months)": (_seasonal_naive, 24, "Assumes each month repeats the same month last year."),
    "Seasonal + yearly change": (_seasonal_drift, 24, "Repeats last year's monthly pattern, shifted by the average year-over-year change."),
}


# ---------------------------------------------------------------- series preparation
def prepare_series(monthly: pd.DataFrame, column: str, source_end: Optional[pd.Timestamp] = None) -> tuple[Optional[pd.DataFrame], str, list[str]]:
    """Return (clean monthly series, problem message, notes). Drops an incomplete last month."""
    notes: list[str] = []
    if monthly.empty or column not in monthly:
        return None, f"No monthly '{column}' data is available.", notes
    s = monthly[["timestamp", column]].rename(columns={column: "value"}).copy()
    if source_end is not None and len(s):
        last_period_end = (s["timestamp"].iloc[-1] + pd.offsets.MonthEnd(0)).normalize()
        if source_end.normalize() < last_period_end and len(s) > 1:
            notes.append(f"The latest month ({s['timestamp'].iloc[-1]:%b %Y}) ends mid-month, so it was excluded from model fitting.")
            s = s.iloc[:-1]
    # Trim leading/trailing empty months.
    valid = s["value"].notna()
    if not valid.any():
        return None, "All monthly values are missing.", notes
    s = s.loc[valid.idxmax(): valid[::-1].idxmax()].reset_index(drop=True)
    gaps = int(s["value"].isna().sum())
    if gaps > max(2, int(0.1 * len(s))):
        return None, f"{gaps} months have no data, which is too many to forecast responsibly.", notes
    s["interpolated"] = s["value"].isna()
    if gaps:
        s["value"] = s["value"].interpolate(limit_direction="both")
        notes.append(f"{gaps} month(s) with no data were filled by straight-line interpolation for modelling only (shown as such in the chart).")
    if len(s) < MIN_PERIODS:
        return None, (f"Only {len(s)} complete monthly periods are available; at least {MIN_PERIODS} are needed to test a forecast honestly. "
                      f"Add {MIN_PERIODS - len(s)} more month(s) of history."), notes
    if np.isclose(s["value"].std(), 0):
        return None, "The series is constant, so a forecast would add no information.", notes
    return s, "", notes


# ---------------------------------------------------------------- validation
def _backtest(y: np.ndarray, fn: Callable, min_train: int, horizon: int = 1) -> tuple[np.ndarray, np.ndarray, list[int]]:
    preds, actuals, idx = [], [], []
    for t in range(min_train, len(y) - horizon + 1):
        train = y[:t]                       # strictly past data
        preds.append(fn(train, horizon)[-1])
        actuals.append(y[t + horizon - 1])
        idx.append(t + horizon - 1)
    return np.array(preds), np.array(actuals), idx


def _scores(pred: np.ndarray, actual: np.ndarray) -> dict:
    err = actual - pred
    nz = actual != 0
    return {
        "MAE": float(np.mean(np.abs(err))),
        "RMSE": float(np.sqrt(np.mean(err ** 2))),
        "MAPE": float(np.mean(np.abs(err[nz] / actual[nz])) * 100) if nz.any() else float("nan"),
    }


def forecast_series(monthly: pd.DataFrame, column: str = "revenue", horizon: int = 6,
                    source_end: Optional[pd.Timestamp] = None, interval: float = 0.8,
                    non_negative: bool = True) -> ForecastResult:
    horizon = int(min(max(horizon, 1), MAX_HORIZON))
    res = ForecastResult(False, target=column, interval_level=interval)
    s, problem, notes = prepare_series(monthly, column, source_end)
    if s is None:
        res.reason = problem
        res.limitations = notes
        return res
    y = s["value"].to_numpy(dtype=float)
    n = len(y)
    min_train = max(6, n // 2)
    if n - min_train < 3:
        res.reason = "Too little history left over to back-test the forecast."
        return res

    rows, store = [], {}
    for name, (fn, need, _) in MODELS.items():
        if n < need + 3:
            continue
        try:
            p, a, idx = _backtest(y, fn, max(min_train, need))
        except Exception:  # noqa: BLE001
            continue
        if len(p) < 3 or not np.all(np.isfinite(p)):
            continue
        sc = _scores(p, a)
        sc["Model"] = name
        rows.append(sc)
        store[name] = (p, a, idx)
    if not rows:
        res.reason = "No candidate model could be validated on this history."
        return res
    comp = pd.DataFrame(rows).set_index("Model")
    best = comp["MAE"].idxmin()
    naive_mae = comp.loc["Naive (repeat last period)", "MAE"] if "Naive (repeat last period)" in comp.index else np.nan
    p, a, idx = store[best]
    errors = a - p
    fn = MODELS[best][0]
    point = np.asarray(fn(y, horizon), dtype=float)

    # Empirical interval from out-of-sample 1-step errors, widened with sqrt(horizon).
    lo_q, hi_q = (1 - interval) / 2, 1 - (1 - interval) / 2
    if len(errors) >= 6:
        lo_e, hi_e = np.quantile(errors, [lo_q, hi_q])
    else:
        sd = errors.std(ddof=1) if len(errors) > 1 else abs(errors).mean()
        from scipy.stats import norm
        lo_e, hi_e = norm.ppf(lo_q) * sd, norm.ppf(hi_q) * sd
    widen = np.sqrt(np.arange(1, horizon + 1))
    lower, upper = point + lo_e * widen, point + hi_e * widen
    if non_negative:
        point, lower, upper = np.maximum(point, 0), np.maximum(lower, 0), np.maximum(upper, 0)
    ts = pd.date_range(s["timestamp"].iloc[-1] + pd.offsets.MonthBegin(1), periods=horizon, freq="MS")
    res.forecast = pd.DataFrame({"timestamp": ts, "point": point, "lower": lower, "upper": upper})
    res.history = s
    res.backtest = pd.DataFrame({"timestamp": s["timestamp"].iloc[idx].to_numpy(), "actual": a, "predicted": p})
    inside = float(np.mean((a >= p + lo_e) & (a <= p + hi_e)))
    sc = _scores(p, a)
    res.metrics = {**sc, "baseline_MAE": float(naive_mae), "beats_baseline": bool(sc["MAE"] < naive_mae) if best != "Naive (repeat last period)" else False,
                   "improvement_vs_baseline_pct": float((1 - sc["MAE"] / naive_mae) * 100) if naive_mae and best != "Naive (repeat last period)" else 0.0,
                   "backtest_points": int(len(a)), "interval_coverage": inside}
    res.comparison = comp.reset_index()[["Model", "MAE", "RMSE", "MAPE"]].sort_values("MAE").reset_index(drop=True)
    res.model = best
    res.model_description = MODELS[best][2]
    res.available = True
    res.assumptions = [
        f"Uses {n} complete monthly periods ({s['timestamp'].iloc[0]:%b %Y} – {s['timestamp'].iloc[-1]:%b %Y}).",
        "Assumes recent patterns continue; no planned price changes, promotions, new products or market shocks are included.",
        f"Model chosen by rolling-origin back-test over {len(a)} past months (each forecast used only earlier data).",
    ] + notes
    res.limitations = [
        f"The {int(interval*100)}% interval is an empirical range built from past forecast errors. It says where about {int(interval*100)}% "
        "of comparable past outcomes fell — it is not the probability of any specific business event.",
        "Short histories cannot reliably capture seasonality or long-term trends.",
        "Accuracy gets worse further into the future; treat later months as rough guidance.",
    ]
    if best == "Naive (repeat last period)":
        res.limitations.append("No tested model beat the naive baseline, so this forecast is just the latest value carried forward.")
    if horizon > n // 3:
        res.limitations.append("The forecast horizon is long relative to the available history.")
    return res


def apply_scenario(fc: pd.DataFrame, change_pct: float) -> pd.DataFrame:
    """What-if scenario: scales the forecast by a user-chosen percentage. Not a prediction."""
    out = fc.copy()
    f = 1 + change_pct / 100.0
    for c in ("point", "lower", "upper"):
        out[c] = out[c] * f
    return out


def risk_indicators(monthly: pd.DataFrame) -> list[dict]:
    """Rule-based risk indicators computed from history. These are *indicators*, not probabilities."""
    out: list[dict] = []
    if monthly.empty:
        return out
    if "revenue" in monthly and monthly["revenue"].notna().sum() >= 6:
        r = monthly["revenue"].dropna()
        cv = float(r.std(ddof=1) / r.mean()) if r.mean() else np.nan
        if np.isfinite(cv):
            level = "High" if cv > 0.5 else "Medium" if cv > 0.25 else "Low"
            out.append({"indicator": "Revenue volatility", "level": level,
                        "detail": f"Monthly revenue varies by {cv:.0%} of its average (coefficient of variation)."})
        last3, prev3 = r.tail(3).mean(), r.iloc[-6:-3].mean()
        if prev3:
            ch = (last3 - prev3) / abs(prev3)
            level = "High" if ch < -0.15 else "Medium" if ch < -0.05 else "Low"
            out.append({"indicator": "Recent sales momentum", "level": level,
                        "detail": f"Average of the last 3 months is {ch:+.1%} versus the 3 months before."})
    if "calc_profit" in monthly and monthly["calc_profit"].notna().sum() >= 3:
        p = monthly["calc_profit"].dropna()
        neg = int((p < 0).sum())
        level = "High" if neg / len(p) > 0.3 else "Medium" if neg else "Low"
        out.append({"indicator": "Loss-making months", "level": level, "detail": f"{neg} of {len(p)} months had a loss."})
    if "revenue" in monthly and "expenses" in monthly:
        both = monthly[["revenue", "expenses"]].dropna()
        if len(both) >= 6:
            rg = both["revenue"].tail(3).mean() / both["revenue"].head(3).mean() - 1 if both["revenue"].head(3).mean() else np.nan
            eg = both["expenses"].tail(3).mean() / both["expenses"].head(3).mean() - 1 if both["expenses"].head(3).mean() else np.nan
            if np.isfinite(rg) and np.isfinite(eg):
                level = "High" if eg - rg > 0.15 else "Medium" if eg > rg else "Low"
                out.append({"indicator": "Costs growing faster than sales", "level": level,
                            "detail": f"Expenses changed {eg:+.1%} while revenue changed {rg:+.1%} (first 3 vs last 3 months)."})
    return out
