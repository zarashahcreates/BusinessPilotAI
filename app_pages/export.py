from datetime import datetime

import streamlit as st

from businesspilot.analysis import detect_numeric_insights, profile_data
from businesspilot.formatters import slug_filename
from businesspilot.history import library, save_report
from businesspilot.mapping import resolve_report_type
from businesspilot.reports import make_docx, make_pdf, make_xlsx
from businesspilot.state import require_data, roles

data = require_data()
mapped = roles()
profile = profile_data(data)
insights = detect_numeric_insights(data, currency=st.session_state.currency, roles=mapped)
report_type = resolve_report_type(data, st.session_state.report_type, mapped)
narrative = st.session_state.get("narrative") or (
    "Analysis not generated yet. This export contains computed data summaries only. "
    "Open Insights to draft the narrative first."
)
stamp = datetime.now().strftime("%Y%m%d")
base = slug_filename(f"{st.session_state.business_name}_{report_type}_{stamp}")

st.title("Export")
st.caption("Downloads use the current workspace, mapping, and narrative. Nothing is sent anywhere unless you enabled an AI key.")

pdf_bytes = make_pdf(
    st.session_state.business_name,
    report_type,
    st.session_state.period_label,
    narrative,
    data,
    insights,
    profile,
)
docx_bytes = make_docx(
    st.session_state.business_name,
    report_type,
    st.session_state.period_label,
    narrative,
    data,
    insights,
    profile,
)
xlsx_bytes = make_xlsx(data, insights, profile, narrative)

d1, d2, d3 = st.columns(3)
with d1:
    st.download_button("Download PDF", pdf_bytes, file_name=f"{base}.pdf", mime="application/pdf", width="stretch", icon=":material/picture_as_pdf:")
with d2:
    st.download_button(
        "Download Word",
        docx_bytes,
        file_name=f"{base}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        width="stretch",
        icon=":material/description:",
    )
with d3:
    st.download_button(
        "Download Excel",
        xlsx_bytes,
        file_name=f"{base}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
        icon=":material/table_view:",
    )

if st.button("Save snapshot to session library", icon=":material/bookmark:"):
    save_report(
        {
            "business_name": st.session_state.business_name,
            "report_type": report_type,
            "period": st.session_state.period_label,
            "rows": int(len(data)),
            "quality": profile.get("quality_score"),
            "narrative_preview": narrative[:280],
        }
    )
    st.success("Saved in this browser session.")

items = library()
if items:
    st.subheader("Session library")
    st.dataframe(items, alt="Reports saved in the current session")

st.subheader("Pack contents")
st.markdown(
    f"""
- Business: **{st.session_state.business_name}**
- Type: **{report_type}**
- Period: **{st.session_state.period_label}**
- Rows: **{len(data):,}**
- Indicators: **{len(insights)}**
"""
)
