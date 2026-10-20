"""Pages for getting data in: Home, Upload, Review and History."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import config, db, ingestion, metrics as M
from ..demo import make_demo_data
from ..ingestion import IngestResult
from ..pipeline import fingerprint
from ..schema import ROLES, Mapping, assess_quality
from . import charts_ui, state, theme
from .compat import button, download, table

NONE = "— not in my data —"
DEMO_KEY = ("__demo__", 0)


# ------------------------------------------------------------------ helpers
def empty_state(message: str, target: str = "Upload", label: str = "Go to Upload") -> None:
    st.info(message)
    st.button(label, on_click=state.go, args=(target,), type="primary")


def unsaved_work() -> bool:
    s = st.session_state
    return state.has_data() and (s.analysis_id is None or s.saved_fp != s.raw_fp)


def start_new_flow(source: str) -> None:
    """Start a fresh analysis, but never silently throw away unsaved work."""
    if unsaved_work():
        st.session_state.confirm_new = True
    else:
        state.reset_all()
    state.go("Upload")


def default_name() -> str:
    return f"Analysis {pd.Timestamp.now():%d %b %Y %H:%M}"


def save_current(name: str, with_reports: bool = True) -> int:
    """Persist the current analysis (and any generated reports). Raises db.StorageError on failure."""
    s = st.session_state
    settings = {"mapping": s.mapping.columns if s.mapping else {}, "currency": s.currency, "business_name": s.business_name,
                "horizon": s.horizon}
    aid = db.save_analysis(name or default_name(), s.business_name, s.raw, settings, analysis_id=s.analysis_id)
    if with_reports and s.exports and s.get("saved_exports_key") != s.exports_key:
        rtype = s.get("report_type_generated", "Report")
        for ext, (fname, data) in s.exports.items():
            db.save_report_file(aid, rtype, ext, fname, data)
        s.saved_exports_key = s.exports_key
    s.analysis_id, s.analysis_name, s.saved_fp = aid, name or default_name(), s.raw_fp
    return aid


def open_saved(aid: int) -> None:
    try:
        settings, df, _ = db.load_analysis(aid)
    except db.StorageError as exc:
        st.session_state.flash = ("error", str(exc))
        return
    s = st.session_state
    state.reset_all()
    s.raw, s.raw_fp = df, fingerprint(df)
    s.mapping = Mapping(columns={k: v for k, v in settings.get("mapping", {}).items() if v in df.columns}, confidence={})
    s.mapping_confirmed = True
    s.business_name, s.currency, s.horizon = settings.get("business_name", "My Business"), settings.get("currency", ""), settings.get("horizon", 6)
    s.analysis_id, s.saved_fp = aid, s.raw_fp
    s.analysis_name = next((a["name"] for a in db.list_analyses() if a["id"] == aid), "")
    s.nav = "Analyze"


def confirm_new_banner() -> None:
    s = st.session_state
    if not s.confirm_new:
        return
    with st.container(border=True):
        st.warning("You have an analysis that has not been saved. Starting a new one will remove it from this screen.")
        c1, c2, c3 = st.columns(3)
        if c1.button("Save, then start new", type="primary", key="w_save_new"):
            try:
                save_current(s.analysis_name or default_name())
                s.pending_reset = True
                st.rerun()
            except db.StorageError as exc:
                st.error(f"Could not save: {exc}")
        if c2.button("Discard and start new", key="w_discard_new"):
            s.pending_reset = True
            st.rerun()
        if c3.button("Cancel", key="w_cancel_new"):
            s.confirm_new = False
            st.rerun()


# ------------------------------------------------------------------ Home
def render_home() -> None:
    theme.hero("Understand your business in minutes",
               "Upload your sales or financial data and BusinessPilot AI checks it, calculates the numbers, shows interactive charts, "
               "explains what they mean and builds a report you can download.")
    confirm_new_banner()
    c1, c2, _ = st.columns([1, 1, 2])
    c1.button("Start new analysis", type="primary", on_click=start_new_flow, args=("home",), key="w_home_new")
    c2.button("Upload business data", on_click=state.go, args=("Upload",), key="w_home_upload")
    if state.has_data():
        st.success(f"Current dataset: {len(st.session_state.raw):,} rows loaded. Continue where you left off:")
        st.button("Continue analysis →", on_click=state.go, args=("Analyze",), key="w_home_continue")

    st.markdown("#### How it works")
    cols = st.columns(5)
    for i, (c, (t, d)) in enumerate(zip(cols, [
        ("Upload", "CSV, Excel, JSON, PDF, Word, text or images — or type data in."),
        ("Review", "Check the preview and confirm what each column means."),
        ("Analyze", "See your key numbers and interactive charts."),
        ("Insights", "Read plain-language findings, risks and next steps."),
        ("Report", "Download PDF, Word or Excel reports."),
    ]), 1):
        with c:
            theme.card(t, d, i)

    st.markdown("#### Recent analyses")
    try:
        recent = db.list_analyses()[:3]
    except db.StorageError as exc:
        recent = []
        st.warning(f"Saved analyses are unavailable: {exc}")
    if recent:
        for a in recent:
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                c1.markdown(f"**{theme.esc(a['name'])}**  \n<span class='bp-muted'>{theme.esc(a['business_name'] or '')} · {a['row_count']:,} rows · "
                            f"saved {theme.esc(a['updated_at'][:16].replace('T', ' '))} · {a['n_reports']} report file(s)</span>", unsafe_allow_html=True)
                c2.button("Open", key=f"w_home_open_{a['id']}", on_click=open_saved, args=(a["id"],))
    else:
        st.caption("Nothing saved yet. Analyses you choose to save appear here (stored on this computer, in the app's data folder).")

    st.markdown("#### What it can do")
    a, b, c = st.columns(3)
    with a:
        theme.card("Understands your columns", "Finds revenue, costs, dates, products and customers automatically — and lets you correct it.")
    with b:
        theme.card("Honest forecasting", "Back-tested forecasts with uncertainty ranges. If there is too little history, it tells you instead of guessing.")
    with c:
        theme.card("Works without AI", "All numbers come from code, not an AI model. An optional AI key adds plain-language commentary.")


# ------------------------------------------------------------------ Upload
def load_demo() -> None:
    """Callback: load the synthetic demo dataset (runs before widgets are created, so it may set their keys)."""
    s = st.session_state
    df = make_demo_data()
    res = IngestResult("Demo data (synthetic).csv", table=df, note=f"Synthetic demonstration data: {len(df):,} rows.", level="warning")
    s.results = [r for k, r in zip(s.result_keys, s.results) if k != DEMO_KEY] + [res]
    s.result_keys = [k for k in s.result_keys if k != DEMO_KEY] + [DEMO_KEY]
    s.business_name, s.currency = "Demo Coffee Co. (synthetic)", "$"
    state.rebuild_raw()


def _process_uploads(files) -> None:
    s = st.session_state
    if len(files) > config.MAX_FILES:
        st.error(f"Please upload at most {config.MAX_FILES} files at a time. Only the first {config.MAX_FILES} are used.")
        files = files[: config.MAX_FILES]
    existing = dict(zip(s.result_keys, s.results))
    keys, results = [], []
    bar = st.progress(0.0, text="Reading files…") if len(files) > 1 else None
    for i, f in enumerate(files):
        k = (f.name, f.size)
        if k not in existing:
            with st.spinner(f"Reading {f.name}…"):
                existing[k] = ingestion.load_file(f.name, f.getvalue())
        keys.append(k); results.append(existing[k])
        if bar:
            bar.progress((i + 1) / len(files), text=f"Read {i + 1} of {len(files)} files")
    if bar:
        bar.empty()
    if DEMO_KEY in s.result_keys and not files:   # uploading real files replaces the demo
        keys.append(DEMO_KEY); results.append(existing[DEMO_KEY])
    if keys != list(s.result_keys):
        s.result_keys, s.results = keys, results
        state.rebuild_raw()


def _show_results() -> None:
    for r in st.session_state.results:
        text = f"**{theme.esc(r.filename)}** — {theme.esc(r.note)}"
        {"success": st.success, "warning": st.warning, "error": st.error}[r.level](text)
        for w in r.warnings:
            st.caption(w)
        if r.text_only and r.raw_text:
            with st.expander(f"Text found in {r.filename}"):
                st.text(r.raw_text[:3000])


def render_upload() -> None:
    s = st.session_state
    theme.progress("Upload", state.done_steps())
    st.header("Upload your business data")
    st.caption(f"Supported: CSV, Excel (.xlsx, .xls), JSON, TXT, PDF, Word (.docx), and images (needs OCR). Up to {config.MAX_FILES} files, {config.MAX_FILE_MB} MB each. "
               "Files are processed inside this app; nothing is sent elsewhere unless you turn on AI commentary later.")
    confirm_new_banner()
    tab_files, tab_manual, tab_demo = st.tabs(["Upload files", "Type data in", "Try demo data"])
    with tab_files:
        ver = s.get("uploader_version", 0)
        files = st.file_uploader("Drag and drop files here", type=config.SUPPORTED_EXTENSIONS, accept_multiple_files=True, key=f"w_upload_{ver}",
                                 help="Use one row per sale, invoice, product or period, with a header row.")
        if files is not None:
            _process_uploads(list(files))
        if not ingestion.ocr_available():
            st.caption("Image/scanned-document reading (OCR) is not set up on this computer — see the README to enable it.")
    with tab_manual:
        st.caption("Fill in rows below (add rows with the + at the bottom). Dates like 2026-01-31 work best.")
        template = pd.DataFrame({"date": pd.Series(dtype="str"), "product": pd.Series(dtype="str"), "revenue": pd.Series(dtype="float"),
                                 "expenses": pd.Series(dtype="float"), "quantity": pd.Series(dtype="float")})
        edited = st.data_editor(template, num_rows="dynamic", key="w_manual_editor", hide_index=True)
        with st.expander("…or paste CSV text"):
            pasted = st.text_area("CSV (first line = column names)", key="w_manual_text", height=140, placeholder="date,product,revenue,expenses\n2026-01-05,Widget,1200,700")
        if button("Use this data", key="w_manual_use", type="primary"):
            try:
                if pasted.strip():
                    df = ingestion.parse_manual_data(pasted)
                else:
                    df = edited.dropna(how="all").reset_index(drop=True)
                    if df.empty:
                        raise ValueError("Please enter at least one row.")
                s.manual_df = df
                state.rebuild_raw()
                st.success(f"Added {len(df):,} row(s).")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Could not use this data: {exc}")
    with tab_demo:
        st.info("The demo is **synthetic** (computer-generated) data for a fictional coffee shop. It is only for exploring the app — not real results.")
        st.button("Load demo dataset", key="w_demo", on_click=load_demo)

    if s.results:
        st.subheader("Files")
        _show_results()
    if state.has_data():
        st.success(f"Ready: {len(s.raw):,} rows × {s.raw.shape[1]} columns.")
        c1, c2 = st.columns([1, 3])
        c1.button("Continue to Review →", type="primary", on_click=state.go, args=("Review",), key="w_up_continue")
        if s.analysis_id is not None and not s.results:
            c2.caption(f"Loaded from saved analysis “{s.analysis_name}”.")
    else:
        st.caption("No data yet. Upload a file, type some rows, or try the demo.")


# ------------------------------------------------------------------ Review
def render_review() -> None:
    s = st.session_state
    theme.progress("Review", state.done_steps())
    st.header("Review your data")
    if not state.has_data():
        return empty_state("There is no data to review yet.")
    raw = s.raw
    shown = raw.drop(columns=["source_file"], errors="ignore")
    bundle = state.current_bundle()
    q = bundle.quality
    c = st.columns(5)
    c[0].metric("Rows", f"{q.rows:,}")
    c[1].metric("Columns", f"{q.columns:,}")
    c[2].metric("Blank cells", f"{q.missing_cells:,}", help="Cells with no value. They are left out of calculations, never filled in.")
    c[3].metric("Duplicate rows", f"{q.duplicate_rows:,}", help="Exact repeats of another row. They are NOT removed automatically.")
    c[4].metric("Quality score", f"{q.score}/100", help="Starts at 100 and loses points for blank cells, duplicate rows and values that could not be read.")
    st.caption("Preview (first 100 rows)")
    table(shown.head(100))

    with st.expander(f"Data-quality checks ({len(q.issues)})", expanded=bool(q.issues)):
        if q.issues:
            for i in q.issues:
                st.warning(i)
        else:
            st.success("No problems found.")
        fig = charts_ui.missing(q.per_column)
        if fig:
            charts_ui.show(fig, "rev_missing")
        table(q.per_column)

    st.subheader("What does each column mean?")
    st.caption("We guessed this from the column names and contents. Change anything that is wrong — the whole app updates.")
    cols = list(shown.columns)
    mapping = s.mapping or Mapping()
    new_cols: dict[str, str] = {}
    essentials = ["date", "revenue", "expenses", "product", "quantity", "customer"]
    others = [r for r in ROLES if r not in essentials]

    def role_select(role: str, container) -> None:
        key = f"map_{role}"
        if key not in s:
            s[key] = mapping.columns.get(role, NONE)
        if s[key] not in cols + [NONE]:
            s[key] = NONE
        label = ROLES[role]["label"] + ("  (auto-detected)" if mapping.confidence.get(role) and s[key] == mapping.columns.get(role) else "")
        v = container.selectbox(label, [NONE] + cols, key=key)
        if v != NONE:
            new_cols[role] = v

    grid = st.columns(3)
    for i, r in enumerate(essentials):
        role_select(r, grid[i % 3])
    with st.expander("More business fields (cost of goods, category, stock, marketing…)"):
        grid2 = st.columns(3)
        for i, r in enumerate(others):
            role_select(r, grid2[i % 3])
    if new_cols != mapping.columns:
        s.mapping = Mapping(columns=new_cols, confidence={k: v for k, v in mapping.confidence.items() if new_cols.get(k) == mapping.columns.get(k)})
        s.mapping_confirmed = False
        st.rerun()
    dup = [c for c in set(new_cols.values()) if list(new_cols.values()).count(c) > 1]
    if dup:
        st.warning("The same column is used for more than one field: " + ", ".join(map(str, dup)) + ". Check that this is intended.")

    st.subheader("What can be analyzed")
    labels = {"revenue": "Revenue and sales", "expenses": "Expenses and costs", "profit": "Profit and margin", "time": "Trends over time (2+ months of dates)",
              "products": "Product performance", "customers": "Customer analysis", "marketing": "Marketing performance", "inventory": "Inventory",
              "expense_breakdown": "Expense breakdown by category", "forecast": "Forecasting (12+ months of revenue history)"}
    cc = st.columns(2)
    for i, (k, lab) in enumerate(labels.items()):
        ok = bundle.avail.get(k)
        cc[i % 2].markdown(f"{'✅' if ok else '▫️'} {lab}" + ("" if ok else " — <span class='bp-muted'>not available with the current column mapping</span>"), unsafe_allow_html=True)
    if not (bundle.avail["revenue"] or bundle.avail["expenses"]):
        st.warning("No revenue or expense column is selected, so only a general data overview is possible. Pick the right columns above if they exist.")
    for note in bundle.std.log:
        st.caption("• " + note)
    st.button("Looks right — analyze →", type="primary", key="w_rev_ok",
              on_click=lambda: (s.__setitem__("mapping_confirmed", True), state.go("Analyze")))


# ------------------------------------------------------------------ History
def render_history() -> None:
    s = st.session_state
    st.header("Saved analyses")
    st.caption("Saved on this computer in the app's data folder. They survive restarting the app but are not shared with other devices or people.")
    if s.flash:
        {"error": st.error, "success": st.success}.get(s.flash[0], st.info)(s.flash[1])
        s.flash = None
    if state.has_data():
        with st.container(border=True):
            st.markdown("**Save your current work**")
            name = st.text_input("Name", value=s.analysis_name or default_name(), key="w_hist_name")
            if button("Save current analysis", key="w_hist_save", type="primary"):
                try:
                    save_current(name)
                    st.success("Saved.")
                except db.StorageError as exc:
                    st.error(f"Could not save: {exc}")
    try:
        items = db.list_analyses()
    except db.StorageError as exc:
        return st.error(f"Could not read saved analyses: {exc}")
    if not items:
        return st.info("No saved analyses yet.")
    for a in items:
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"**{theme.esc(a['name'])}**  \n<span class='bp-muted'>{theme.esc(a['business_name'] or '')} · {a['row_count']:,} rows · "
                        f"updated {theme.esc(a['updated_at'][:16].replace('T', ' '))}</span>", unsafe_allow_html=True)
            c2.button("Open", key=f"w_open_{a['id']}", on_click=open_saved, args=(a["id"],))
            r1, r2, r3 = st.columns(3)
            with r1.expander("Rename"):
                nn = st.text_input("New name", value=a["name"], key=f"w_rn_{a['id']}")
                if st.button("Rename", key=f"w_rnb_{a['id']}"):
                    try:
                        db.rename_analysis(a["id"], nn); st.rerun()
                    except db.StorageError as exc:
                        st.error(str(exc))
            with r2.expander(f"Reports ({a['n_reports']})"):
                try:
                    reps = db.list_reports(a["id"])
                except db.StorageError as exc:
                    reps = []; st.error(str(exc))
                if not reps:
                    st.caption("No report files stored.")
                for r in reps:
                    try:
                        fname, data = db.read_report_file(r["id"])
                        download(f"{r['fmt'].upper()} · {r['report_type']} ({r['created_at'][:10]})", data, fname, "application/octet-stream", key=f"w_dl_{r['id']}")
                    except db.StorageError as exc:
                        st.caption(f"{r['filename']}: {exc}")
            with r3.expander("Delete"):
                st.warning("This permanently deletes the analysis and its stored report files.")
                sure = st.checkbox("Yes, delete it", key=f"w_delchk_{a['id']}")
                if st.button("Delete permanently", key=f"w_del_{a['id']}", disabled=not sure):
                    try:
                        db.delete_analysis(a["id"])
                        if s.analysis_id == a["id"]:
                            s.analysis_id, s.saved_fp = None, None
                        st.rerun()
                    except db.StorageError as exc:
                        st.error(str(exc))
