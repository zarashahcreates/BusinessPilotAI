import pandas as pd
import streamlit as st

from businesspilot.analysis import compute_kpis, time_series
from businesspilot.formatters import money, percent
from businesspilot.forecasting import linear_forecast, what_if_profit
from businesspilot.prediction import train_probability_model
from businesspilot.state import require_data, roles

data = require_data()
mapped = roles()
kpis = compute_kpis(data, mapped)

st.title("Models")
st.caption("Simple baselines only. They describe the table you loaded; they are not a guarantee of what happens next.")

forecast_tab, whatif_tab, probability_tab = st.tabs(
    ["Trend forecast", "What-if", "Probability model"],
    on_change="rerun",
)

if forecast_tab.open:
    series = time_series(data, mapped)
    horizon = st.slider("Days to project", min_value=7, max_value=60, value=14)
    if series.empty:
        st.info("Map a date column and a numeric value column to build a trend line.")
    else:
        forecast = linear_forecast(series, periods=horizon)
        history = series.rename(columns={"Value": "Actual"})
        if forecast.empty:
            st.warning("Need at least five dated points to fit a trend.")
        else:
            combined = pd.merge(history, forecast[["Date", "Forecast"]], on="Date", how="outer").sort_values("Date")
            st.line_chart(
                combined,
                x="Date",
                y=["Actual", "Forecast"],
                alt="Historical daily totals with a linear trend projection",
            )
            slope = float(forecast["slope_per_day"].iloc[0])
            st.metric("Fitted daily slope", money(slope, st.session_state.currency), border=True)
            st.caption("Ordinary least squares on daily totals, floored at zero. Not seasonal, not causal.")
            st.dataframe(forecast.drop(columns=["slope_per_day"]), alt="Projected daily totals")

if whatif_tab.open:
    st.markdown("Adjust revenue and expenses to see the mechanical effect on profit. This is arithmetic, not a forecast.")
    if kpis.get("revenue") is None and kpis.get("expenses") is None:
        st.info("Map revenue and expense columns first.")
    else:
        lift = st.slider("Revenue change", min_value=-30, max_value=40, value=5, format="%d%%")
        cut = st.slider("Expense reduction", min_value=0, max_value=30, value=3, format="%d%%")
        result = what_if_profit(kpis.get("revenue"), kpis.get("expenses"), lift, cut)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Current profit", money(kpis.get("profit"), st.session_state.currency), border=True)
        c2.metric("Scenario revenue", money(result["revenue"], st.session_state.currency), border=True)
        c3.metric("Scenario expenses", money(result["expenses"], st.session_state.currency), border=True)
        c4.metric("Scenario profit", money(result["profit"], st.session_state.currency), border=True)
        st.caption(f"Scenario margin {percent(result['margin_pct'])}.")

if probability_tab.open:
    st.markdown(
        "Train a logistic baseline only if the table contains a historical outcome column, such as payment status. "
        "Do not treat this as a probability for events that are not labelled in the data."
    )
    candidates = [c for c in data.columns if not str(c).startswith("__")]
    default = mapped.get("status") if mapped.get("status") in candidates else None
    target = st.selectbox("Outcome column", candidates, index=candidates.index(default) if default in candidates else 0)
    if st.button("Train and evaluate", type="primary", icon=":material/query_stats:"):
        try:
            st.session_state.model_result = train_probability_model(data, target)
        except Exception as exc:
            st.error(str(exc))
    result = st.session_state.get("model_result")
    if result:
        m1, m2, m3 = st.columns(3)
        m1.metric("Test accuracy", f"{result['accuracy']:.3f}", border=True)
        m2.metric("Brier score", f"{result['brier_score']:.3f}", border=True, help="Lower is better.")
        m3.metric("Held-out rows", f"{result['n_test']:,}", border=True)
        st.caption(result["evaluation"])
        st.dataframe(result["class_balance"], alt="Share of each outcome class in the labelled data")
        st.dataframe(result["class_report"], alt="Precision and recall by class on the holdout set")
        st.dataframe(result["predictions"].head(200), alt="Holdout predictions and class probabilities")
        st.caption("Educational starter model. Check leakage, calibration, and a time-aware split before any operational use.")
