import streamlit as st

from businesspilot.analysis import detect_numeric_insights, profile_data
from businesspilot.mapping import resolve_report_type
from businesspilot.sample_data import load_sample, sample_catalog
from businesspilot.state import current_data, has_data, roles, set_workspace

st.title("BusinessPilot AI")
st.caption("Turn operational tables into a board-ready briefing, without dressing guesses up as facts.")

intro, actions = st.columns((1.7, 1), gap="large")
with intro:
    st.markdown(
        """
Load structured business data, map the important fields, and the workspace will
profile quality, compute KPIs, chart the mix, draft an evidence-based narrative,
and export PDF, Word, and Excel packs.
"""
    )
    st.markdown(
        ":blue-badge[CSV / Excel / PDF] :green-badge[Sample data] :orange-badge[Period comparison] :violet-badge[Optional AI]"
    )

with actions:
    with st.container(border=True):
        st.subheader("Start in 30 seconds")
        catalog = sample_catalog()
        sample_name = st.selectbox("Sample dataset", list(catalog.keys()), help=catalog["Retail sales"])
        st.caption(catalog[sample_name])
        if st.button("Load sample", type="primary", width="stretch", icon=":material/play_arrow:"):
            frame = load_sample(sample_name)
            set_workspace(frame, [f"Loaded sample dataset: {sample_name}."], sample_name=sample_name)
            if sample_name == "Retail sales":
                st.session_state.business_name = "Harbor Home"
                st.session_state.period_label = "Jun–Sep 2026"
            elif sample_name == "Service invoices":
                st.session_state.business_name = "Brightline Advisory"
                st.session_state.period_label = "Weekly invoices 2026"
            else:
                st.session_state.business_name = "Harbor Home warehouse"
                st.session_state.period_label = "Current stock snapshot"
            st.success(f"Loaded {len(frame):,} rows.")
            st.rerun()
        st.page_link("app_pages/data_studio.py", label="Or upload your own files", icon=":material/upload_file:")

st.subheader("How the workspace is organised")
c1, c2, c3, c4 = st.columns(4, border=True)
c1.markdown("**1. Data studio**")
c1.caption("Upload, paste, map columns, and clean obvious issues.")
c2.markdown("**2. Dashboard**")
c2.caption("KPIs, trends, mix, and period comparison from mapped fields.")
c3.markdown("**3. Insights**")
c3.caption("Evidence-based narrative and questions grounded in the table.")
c4.markdown("**4. Export**")
c4.caption("PDF, Word, and Excel with the same numbers you see on screen.")

data = current_data()
if not has_data():
    st.info("No dataset is loaded yet. Use a sample above or open Data studio.", icon=":material/info:")
else:
    profile = profile_data(data)
    mapped = roles()
    insights = detect_numeric_insights(data, currency=st.session_state.currency, roles=mapped)
    report_type = resolve_report_type(data, st.session_state.report_type, mapped)
    st.subheader("Current workspace")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Rows", f"{profile['rows']:,}", border=True)
    m2.metric("Columns", f"{profile['columns']:,}", border=True)
    m3.metric("Quality score", f"{profile['quality_score']}/100", border=True)
    m4.metric("Report type", report_type, border=True)
    if insights:
        st.caption("Detected indicators")
        with st.container(horizontal=True):
            for label, value in list(insights.items())[:4]:
                st.metric(label, value, border=True)
    st.page_link("app_pages/dashboard.py", label="Open dashboard", icon=":material/dashboard:")
