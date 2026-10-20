import pandas as pd
import streamlit as st

from businesspilot.analysis import (
    category_breakdown,
    comparison_frame,
    compute_kpis,
    detect_anomalies,
    detect_numeric_insights,
    filter_by_date,
    kpi_delta,
    parse_dates,
    profile_data,
    time_series,
)
from businesspilot.formatters import compact_number, money, percent
from businesspilot.mapping import resolve_report_type
from businesspilot.state import require_data, roles

data = require_data()
mapped = roles()
currency = st.session_state.currency
report_type = resolve_report_type(data, st.session_state.report_type, mapped)

st.title("Dashboard")
st.caption(f"{st.session_state.business_name} · {report_type} · {st.session_state.period_label}")

date_col = mapped.get("date")
filtered = data
previous = pd.DataFrame()
if date_col:
    parsed = parse_dates(data, date_col)
    valid = parsed.dropna()
    if not valid.empty:
        min_day, max_day = valid.min().date(), valid.max().date()
        picked = st.date_input(
            "Date range",
            value=(min_day, max_day),
            min_value=min_day,
            max_value=max_day,
            format="YYYY-MM-DD",
        )
        if isinstance(picked, tuple) and len(picked) == 2:
            start, end = picked
        else:
            start, end = min_day, max_day
        filtered = filter_by_date(data, date_col, start, end)
        span = (pd.Timestamp(end) - pd.Timestamp(start)).days + 1
        prev_end = pd.Timestamp(start) - pd.Timedelta(days=1)
        prev_start = prev_end - pd.Timedelta(days=span - 1)
        previous = filter_by_date(data, date_col, prev_start.date(), prev_end.date())
        st.caption(f"Comparing against the previous {span} day(s) ending {prev_end.date()}.")

kpis = compute_kpis(filtered, mapped)
prev_kpis = compute_kpis(previous, mapped) if not previous.empty else {}
profile = profile_data(filtered)

metric_specs = [
    ("Revenue", kpis.get("revenue"), prev_kpis.get("revenue"), True, "line"),
    ("Expenses", kpis.get("expenses"), prev_kpis.get("expenses"), True, "line"),
    ("Profit", kpis.get("profit"), prev_kpis.get("profit"), True, "area"),
    ("Margin", kpis.get("margin_pct"), prev_kpis.get("margin_pct"), False, "bar"),
]

series = time_series(filtered, mapped, "revenue")
spark = series["Value"].tolist()[-24:] if not series.empty else None

with st.container(horizontal=True):
    for label, current, prior, is_money, chart_type in metric_specs:
        if current is None:
            st.metric(label, "—", border=True)
            continue
        display = money(current, currency) if is_money else percent(current)
        delta = kpi_delta(current, prior)
        if delta is None:
            st.metric(label, display, border=True, chart_data=spark, chart_type=chart_type)
        else:
            delta_display = money(delta, currency) if is_money else round(delta, 1)
            st.metric(
                label,
                display,
                delta=delta_display,
                delta_description="vs previous window",
                border=True,
                chart_data=spark if label != "Margin" else None,
                chart_type=chart_type,
            )

extra1, extra2, extra3, extra4 = st.columns(4)
extra1.metric("Rows in view", f"{kpis['rows']:,}", border=True)
extra2.metric("Quality", f"{profile['quality_score']}/100", border=True)
extra3.metric("Products", compact_number(kpis.get("unique_products")), border=True)
extra4.metric("Customers", compact_number(kpis.get("unique_customers")), border=True)

left, right = st.columns(2, gap="large")
with left:
    with st.container(border=True):
        st.subheader("Trend")
        if series.empty:
            st.info("Map a date column and a revenue, quantity, or stock column to see a trend.")
        else:
            st.line_chart(series, x="Date", y="Value", alt="Daily total of the mapped value field")
with right:
    with st.container(border=True):
        st.subheader("Mix")
        breakdown = category_breakdown(filtered, mapped, "product")
        if breakdown.empty:
            breakdown = category_breakdown(filtered, mapped, "region")
        if breakdown.empty:
            st.info("Map a product or region column to see mix.")
        else:
            st.bar_chart(breakdown, x="Category", y="Value", horizontal=True, alt="Value by mapped category")

region = category_breakdown(filtered, mapped, "region")
if not region.empty:
    st.subheader("Region")
    st.bar_chart(region, x="Category", y="Value", alt="Value by region")

if date_col and not previous.empty:
    st.subheader("Period comparison")
    compare = comparison_frame(kpis, prev_kpis)
    st.dataframe(
        compare,
        alt="Current versus previous window for core metrics",
        column_config={
            "Current": st.column_config.NumberColumn(format="%.2f"),
            "Previous": st.column_config.NumberColumn(format="%.2f"),
            "Change": st.column_config.NumberColumn(format="%.2f"),
            "Change %": st.column_config.NumberColumn(format="%.1f"),
        },
    )

st.subheader("Unusual days")
anomalies = detect_anomalies(series)
if anomalies.empty:
    st.caption("No daily totals sit more than 2.5 standard deviations from the mean.")
else:
    st.dataframe(anomalies, alt="Days whose totals are unusually high or low")

st.subheader("Detail")
st.dataframe(filtered.head(300), alt="Filtered workspace rows", height=340)
