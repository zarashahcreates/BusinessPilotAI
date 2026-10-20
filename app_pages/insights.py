import streamlit as st

from businesspilot.ai_insights import answer_question, build_qa_context, generate_narrative
from businesspilot.analysis import category_breakdown, compute_kpis, detect_anomalies, detect_numeric_insights, profile_data, time_series
from businesspilot.formatters import money
from businesspilot.mapping import resolve_report_type
from businesspilot.state import require_data, roles

data = require_data()
mapped = roles()
profile = profile_data(data)
insights = detect_numeric_insights(data, currency=st.session_state.currency, roles=mapped)
kpis = compute_kpis(data, mapped)
report_type = resolve_report_type(data, st.session_state.report_type, mapped)
series = time_series(data, mapped)
products = category_breakdown(data, mapped, "product", top_n=5)
mix_lines = [f"{row.Category}: {money(row.Value, st.session_state.currency)}" for row in products.itertuples()] if not products.empty else []
anomalies = detect_anomalies(series)
extra_facts = {
    "mix": mix_lines,
    "anomalies": [
        f"{row.Date}: {row.direction} day at {money(row.Value, st.session_state.currency)}"
        for row in anomalies.head(5).itertuples()
    ]
    if not anomalies.empty
    else [],
}

st.title("Insights")
st.caption("Narrative stays inside the numbers already computed from the workspace.")

left, right = st.columns((1.4, 1), gap="large")
with left:
    if st.button("Generate report analysis", type="primary", icon=":material/auto_awesome:"):
        with st.spinner("Drafting the briefing from workspace facts..."):
            st.session_state.narrative = generate_narrative(
                business_name=st.session_state.business_name,
                report_type=report_type,
                period=st.session_state.period_label,
                profile=profile,
                numeric_insights=insights,
                columns=[str(c) for c in data.columns if not str(c).startswith("__")],
                recommendations=st.session_state.include_recommendations,
                detail=st.session_state.detail,
                extra_facts=extra_facts,
            )
    narrative = st.session_state.get("narrative")
    if narrative:
        st.markdown(narrative)
    else:
        st.info("Generate the analysis when the mapping and date range look right.", icon=":material/notes:")

with right:
    with st.container(border=True):
        st.subheader("Facts used")
        if insights:
            for label, value in insights.items():
                st.markdown(f"**{label}**  \n{value}")
        else:
            st.caption("No mapped KPIs yet.")
        st.caption(f"Quality score {profile['quality_score']}/100")

st.subheader("Ask about this dataset")
context = build_qa_context(data, mapped, profile, insights, kpis, mix_lines)
for message in st.session_state.chat_messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

prompt = st.chat_input("Example: Which mapped KPI is largest?")
if prompt:
    st.session_state.chat_messages.append({"role": "user", "content": prompt})
    reply = answer_question(prompt, context)
    st.session_state.chat_messages.append({"role": "assistant", "content": reply})
    st.rerun()
