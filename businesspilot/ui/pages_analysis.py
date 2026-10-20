"""Analysis-side pages: dashboard, insights and report generation."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import ai_insights, config, db, reports
from ..ai_insights import KINDS, SECTION_TITLES
from ..metrics import customer_monthly, recommend_reports
from ..prediction import apply_scenario, train_probability_model
from . import charts_ui as C
from . import state, theme
from .compat import button, download, table
from .pages_data import default_name, empty_state, save_current


def _need_data() -> bool:
    if state.has_data():
        return False
    empty_state("Upload some data first and this page will fill in automatically.")
    return True


# ------------------------------------------------------------------ Analyze
def _filters(box, bundle) -> None:
    s = st.session_state
    full = bundle.std.df
    with box:
        with st.expander("Filters", expanded=False):
            changed = False
            c = st.columns(3)
            new_range = s.date_range
            if "date" in full and full["date"].notna().any():
                lo, hi = full["date"].min().date(), full["date"].max().date()
                cur = s.date_range or (lo, hi)
                val = c[0].date_input("Date range", value=(cur[0], cur[1]), min_value=lo, max_value=hi, key="flt_dates")
                if isinstance(val, (tuple, list)) and len(val) == 2:
                    new_range = None if (val[0] == lo and val[1] == hi) else (val[0], val[1])
            new_cat = dict(s.cat_filters)
            for i, role in enumerate(("product", "category")):
                if role in full and full[role].notna().any():
                    opts = sorted(full[role].dropna().unique().tolist())[:300]
                    sel = c[i + 1].multiselect(role.title(), opts, default=s.cat_filters.get(role, []), key=f"flt_{role}")
                    if sel:
                        new_cat[role] = sel
                    else:
                        new_cat.pop(role, None)
            if new_range != s.date_range or new_cat != s.cat_filters:
                s.date_range, s.cat_filters = new_range, new_cat
                changed = True
            if bundle.filters_note:
                st.caption(bundle.filters_note)
            if changed:
                st.rerun()


def render_analyze() -> None:
    s = st.session_state
    theme.progress("Analyze", state.done_steps())
    st.header("Business dashboard")
    if _need_data():
        return
    box = st.container()
    b = state.current_bundle()
    _filters(box, b)
    if not s.mapping_confirmed:
        st.info("Using the automatically detected column meanings. You can check or change them in **Review**.")
    if b.data.empty:
        return st.warning("The current filters leave no rows. Widen the date range or clear the product/category filters.")
    st.caption(f"Period: **{b.period}** · {len(b.data):,} rows" + (f" · Currency: {s.currency}" if s.currency else ""))

    if not b.metrics:
        st.warning("No financial metrics could be calculated — no revenue, expense or profit column is mapped. "
                   "Open **Review** and pick the columns that hold your sales and costs.")
    else:
        main = b.metrics[:8]
        for row in range(0, len(main), 4):
            cols = st.columns(4)
            for col, m in zip(cols, main[row:row + 4]):
                col.metric(m.label, m.display, help=f"{m.explanation}  Formula: {m.formula}.  Basis: {m.basis}")
        if len(b.metrics) > 8:
            with st.expander(f"More metrics ({len(b.metrics) - 8})"):
                cols = st.columns(4)
                for i, m in enumerate(b.metrics[8:]):
                    cols[i % 4].metric(m.label, m.display, help=f"{m.explanation}  Formula: {m.formula}.  Basis: {m.basis}")
        with st.expander("What do these metrics mean?"):
            for m in b.metrics:
                st.markdown(f"**{m.label}** — {m.explanation}  \n<span class='bp-muted'>Formula: {theme.esc(m.formula)} · {theme.esc(m.basis)}</span>", unsafe_allow_html=True)

    tabs_wanted = []
    if b.avail["time"] and not b.monthly.empty:
        tabs_wanted.append("Trends")
    if b.avail["products"] and not b.products.empty:
        tabs_wanted.append("Products")
    if b.avail["expense_breakdown"] and not b.expenses.empty:
        tabs_wanted.append("Expenses")
    cm = customer_monthly(b.data) if b.avail["customers"] else pd.DataFrame()
    if not cm.empty:
        tabs_wanted.append("Customers")
    if b.avail["revenue"] and "date" in b.data:
        tabs_wanted.append("Forecast")
    tabs_wanted.append("Data quality")
    for t, obj in zip(tabs_wanted, st.tabs(tabs_wanted)):
        with obj:
            if t == "Trends":
                C.show(C.trend_chart(b.monthly, s.currency), "an_trend")
                freq = st.radio("Sales by", ["Monthly", "Quarterly"], horizontal=True, key="w_freq")
                C.show(C.period_bars(b.monthly, freq, s.currency), "an_period")
                st.caption("Months with no data appear as gaps, not zeros. The last month may be incomplete if your data ends mid-month.")
            elif t == "Products":
                col = b.products.columns[1]
                C.show(C.product_bar(b.products, col, s.currency), "an_prod")
                shown = b.products.rename(columns={"product": "Product", "share": "Share of total"}).copy()
                shown["Share of total"] = (shown["Share of total"] * 100).round(1).astype(str) + "%"
                table(shown)
            elif t == "Expenses":
                C.show(C.expense_chart(b.expenses, s.currency), "an_exp")
            elif t == "Customers":
                C.show(C.customer_chart(cm), "an_cust")
                st.caption("“New” = a customer's first month in this data. Customers who bought before your data begins will appear as new.")
            elif t == "Forecast":
                _forecast_tab(b)
            else:
                q = b.quality
                st.write(f"Quality score **{q.score}/100**. See the **Review** page for details.")
                fig = C.missing(q.per_column)
                if fig:
                    C.show(fig, "an_missing")
                else:
                    st.success("No blank cells.")
    st.button("Next: read the insights →", type="primary", on_click=state.go, args=("Insights",), key="w_an_next")


def _forecast_tab(b) -> None:
    s = st.session_state
    fc = b.forecast
    st.markdown("**Revenue forecast** — a simple, tested projection of future monthly revenue.")
    h = st.slider("How many months ahead?", 3, 12, int(s.horizon), key="w_horizon_slider")
    if h != s.horizon:
        s.horizon = h
        st.rerun()
    if fc is None or not fc.available:
        st.info("A forecast is not available yet. " + (fc.reason if fc else "No revenue history was found."))
        for n in (fc.limitations if fc else []):
            st.caption("• " + n)
    else:
        scen = st.slider("What-if scenario: change expected revenue by (%)", -30, 30, 0, key="w_scen",
                         help="Scales the forecast up or down to explore a what-if. This is NOT a prediction.")
        fshow = fc
        if scen:
            import copy
            fshow = copy.copy(fc)
            fshow.forecast = apply_scenario(fc.forecast, scen)
            st.caption(f"Showing a what-if scenario ({scen:+d}% versus the model forecast).")
        C.show(C.forecast_figure(fshow, s.currency), "fc_main")
        m = fc.metrics
        c = st.columns(4)
        c[0].metric("Model used", fc.model, help=fc.model_description)
        c[1].metric("Typical error (MAPE)", f"{m['MAPE']:.1f}%", help="Average percentage miss when this method was tested on past months.")
        c[2].metric("Average miss (MAE)", f"{m['MAE']:,.0f}", help="Average size of the miss, in your currency units.")
        c[3].metric("Interval coverage", f"{m['interval_coverage']:.0%}", help=f"Share of past months that landed inside the {int(fc.interval_level * 100)}% range.")
        if m["beats_baseline"]:
            st.success(f"This method beat the simplest baseline (repeat last month) by {m['improvement_vs_baseline_pct']:.0f}% in back-testing.")
        else:
            st.warning("No method beat the simplest baseline (repeat last month). Treat this forecast with extra caution.")
        out = fshow.forecast.copy()
        out["timestamp"] = out["timestamp"].dt.strftime("%b %Y")
        table(out.rename(columns={"timestamp": "Month", "point": "Forecast", "lower": "Lower", "upper": "Upper"}).round(2))
        C.show(C.actual_vs_predicted(fc, s.currency), "fc_bt")
        with st.expander("Model comparison (back-test errors; lower is better)"):
            table(fc.comparison.round(2))
        with st.expander("Assumptions and limitations", expanded=True):
            for t in fc.assumptions + fc.limitations:
                st.markdown("- " + t)
    if b.risk:
        st.markdown("**Risk indicators** *(rule-based checks, not probabilities)*")
        table(pd.DataFrame(b.risk).rename(columns={"indicator": "Indicator", "level": "Level", "detail": "Detail"}))
    _probability_tool(b)


def _probability_tool(b) -> None:
    s = st.session_state
    with st.expander("Advanced: estimate the probability of an outcome (needs labelled history)"):
        st.caption("Use this only if your data has a column recording a past outcome (for example 'paid_late' = yes/no). "
                   "The model learns from your history and is tested on held-out rows. It cannot predict events you have no history for.")
        raw = s.raw.drop(columns=["source_file"], errors="ignore")
        cands = [c for c in raw.columns if 2 <= raw[c].nunique(dropna=True) <= 20]
        if not cands:
            return st.info("No column with 2–20 distinct values was found, so there is nothing to predict.")
        target = st.selectbox("Outcome column", ["— select —"] + cands, key="w_target")
        if target != "— select —" and button("Train and test model", key="w_train"):
            try:
                with st.spinner("Training and testing…"):
                    s.prob_result = train_probability_model(raw, target, s.mapping.columns.get("date"))
            except Exception as exc:  # noqa: BLE001
                s.prob_result = None
                st.error(str(exc))
        r = s.prob_result
        if r:
            c = st.columns(3)
            c[0].metric("Accuracy (test)", f"{r['accuracy']:.0%}", help=f"Always guessing the most common outcome scores {r['baseline_accuracy']:.0%}.")
            c[1].metric("Brier score (model)", f"{r['brier_score']:.3f}", help="Lower is better; measures how close the probabilities are to what happened.")
            c[2].metric("Brier score (baseline)", f"{r['baseline_brier']:.3f}", help="Score from just using overall outcome frequencies.")
            (st.success if r["beats_baseline"] else st.warning)(
                "The model is better than the baseline on held-out data." if r["beats_baseline"] else "The model is NOT better than the baseline — do not rely on its probabilities.")
            st.caption(f"{r['evaluation']}  Trained on {r['n_train']:,} rows, tested on {r['n_test']:,}.  {r['meaning']}")
            table(r["predictions"].head(50).round(3))


# ------------------------------------------------------------------ Insights
def render_insights() -> None:
    s = st.session_state
    theme.progress("Insights", state.done_steps())
    st.header("Insights")
    if _need_data():
        return
    b = state.current_bundle()
    rep = b.insights
    st.markdown("Every statement is labelled: " + " ".join(theme.kind_badge(k, v) for k, v in KINDS.items()), unsafe_allow_html=True)
    for sec in ai_insights.SECTIONS:
        items = rep.by_section(sec)
        if not items:
            continue
        st.subheader(SECTION_TITLES[sec])
        for i in items:
            st.markdown(f"- {theme.esc(i.text)} {theme.kind_badge(i.kind, KINDS[i.kind])}", unsafe_allow_html=True)

    st.subheader("AI commentary (optional)")
    if rep.llm_status == "used":
        with st.container(border=True):
            st.markdown("**AI-generated interpretation**")
            st.write(rep.llm_text)
            st.caption(rep.llm_note)
    else:
        if not config.openai_key():
            st.info("AI commentary is **off** because no API key is configured. Everything above works without it. See the README to add `OPENAI_API_KEY`.")
        else:
            st.caption("Clicking the button sends the aggregated figures above (totals, shares and the findings text — **no raw rows**) to OpenAI to write a short commentary.")
            if rep.llm_status == "failed":
                st.warning(rep.llm_note)
            if button("Generate AI commentary", key="w_llm"):
                with st.spinner("Asking the AI service…"):
                    facts = ai_insights.facts_for_llm(rep, b.metrics, b.products)
                    ai_insights.add_llm_commentary(rep, facts)
                s.exports, s.exports_key = None, None
                st.rerun()
    st.button("Next: create a report →", type="primary", on_click=state.go, args=("Reports",), key="w_ins_next")


# ------------------------------------------------------------------ Reports
def _preview(doc) -> None:
    for blk in doc.blocks:
        if blk.kind == "h1":
            st.subheader(blk.text)
        elif blk.kind == "h2":
            st.markdown(f"**{blk.text}**")
        elif blk.kind in ("p", "note"):
            (st.write if blk.kind == "p" else st.caption)(blk.text)
        elif blk.kind == "bullets":
            st.markdown("\n".join(f"- {i}" for i in blk.items))
        elif blk.kind == "table" and blk.rows:
            table(pd.DataFrame(blk.rows[1:], columns=blk.rows[0]))
        elif blk.kind == "image":
            st.image(blk.image, caption=blk.text)


def render_reports() -> None:
    s = st.session_state
    theme.progress("Report", state.done_steps())
    st.header("Create a report")
    if _need_data():
        return
    b = state.current_bundle()
    recs = recommend_reports(b.avail)
    st.markdown("**Recommended for your data**")
    for name, why in recs[:4]:
        st.markdown(f"- **{name}** — {why}")
    mode = st.radio("Report choice", ["Automatic (use the best recommendation)", "I'll choose"], horizontal=True, key="w_rep_mode")
    all_types = config.REPORT_TYPES
    if mode.startswith("Automatic"):
        rtype = recs[0][0]
        st.caption(f"Using: **{rtype}**")
    else:
        rtype = st.selectbox("Report type", all_types, index=all_types.index(recs[0][0]) if recs[0][0] in all_types else 0, key="w_rep_type")
    avail_secs = reports.available_sections(b.avail)
    defaults = reports.default_sections(rtype, b.avail)
    sections = st.multiselect("Sections to include", avail_secs, default=defaults, key=f"w_secs_{rtype}",
                              format_func=lambda x: reports.SECTION_DEFS[x][0])
    st.caption(f"Business name on the report: **{theme.esc(s.business_name)}** (change it under Settings in the sidebar).")
    include_llm = st.checkbox("Include AI commentary", value=b.insights.llm_status == "used", disabled=b.insights.llm_status != "used",
                                help="Available after you generate AI commentary on the Insights page.")
    if not sections:
        return st.warning("Select at least one section.")

    try:
        doc = reports.build_report(b, rtype, sections, s.business_name, include_llm)
    except reports.ReportError as exc:
        return st.error(str(exc))
    with st.expander("Preview report contents"):
        _preview(doc)

    gen_key = (state.analysis_inputs(), rtype, tuple(sections), s.business_name, include_llm, b.insights.llm_status)
    if button("Generate PDF, Word and Excel files", key="w_gen", type="primary"):
        bar = st.progress(0.0, text="Building report…")
        try:
            bar.progress(0.3, text="Creating charts and documents…")
            s.exports = reports.export_all(b, rtype, sections, s.business_name, include_llm)
            s.exports_key, s.report_type_generated = gen_key, rtype
            bar.progress(1.0, text="Done")
        except reports.ReportError as exc:
            s.exports, s.exports_key = None, None
            st.error(f"The report could not be created. {exc}")
        finally:
            bar.empty()
    if s.exports and s.exports_key == gen_key:
        st.success("Your report files are ready.")
        mimes = {"pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                 "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
        cols = st.columns(3)
        for col, (ext, (fname, data)) in zip(cols, s.exports.items()):
            with col:
                download(f"Download {ext.upper()}  ({len(data) / 1024:,.0f} KB)", data, fname, mimes[ext], key=f"w_dl_{ext}")
        st.markdown("**Save to history**")
        name = st.text_input("Name for this analysis", value=s.analysis_name or default_name(), key="w_save_name")
        if button("Save analysis and these files", key="w_save_rep"):
            try:
                save_current(name)
                st.success("Saved. You can reopen it from History.")
            except db.StorageError as exc:
                st.error(f"Could not save: {exc}")
    elif s.exports:
        st.info("Settings changed since the files were generated. Click the button above to create updated files.")
