import streamlit as st

from businesspilot.analysis import column_summary, profile_data
from businesspilot.cleaning import clean_frame
from businesspilot.io_utils import load_uploaded_file, parse_manual_data
from businesspilot.mapping import ROLE_HELP, ROLE_LABELS, infer_column_roles
from businesspilot.sample_data import load_sample, sample_catalog
from businesspilot.state import current_data, has_data, set_workspace

st.title("Data studio")
st.caption("Bring a table in, map the fields that matter, then clean only what you intend to change.")

data_tabs = st.tabs(["Upload", "Enter data", "Sample data", "Clean"], on_change="rerun")

if data_tabs[0].open:
    uploads = st.file_uploader(
        "Upload CSV, Excel, JSON, PDF, or image files",
        type=["csv", "xlsx", "xls", "json", "pdf", "png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
    )
    replace = st.toggle("Replace the current workspace", value=not has_data())
    if st.button("Load files", type="primary", icon=":material/upload_file:") and uploads:
        frames = []
        notes = []
        for uploaded in uploads:
            try:
                table, note = load_uploaded_file(uploaded)
                notes.append(f"{uploaded.name}: {note}")
                if table is not None and not table.empty:
                    table = table.copy()
                    table["__source_file"] = uploaded.name
                    frames.append(table)
            except Exception as exc:
                notes.append(f"{uploaded.name}: could not read file ({exc}).")
        if frames:
            from businesspilot.io_utils import combine_tables

            incoming = combine_tables(frames)
            if replace or not has_data():
                set_workspace(incoming, notes)
            else:
                combined = combine_tables([current_data(), incoming])
                set_workspace(combined, list(st.session_state.source_notes) + notes)
            st.success(f"Workspace now has {len(st.session_state.workspace_df):,} rows.")
            st.rerun()
        else:
            st.error("No tabular rows could be extracted from those files.")

if data_tabs[1].open:
    st.markdown("Enter rows as CSV. The first line must contain column names.")
    manual_default = (
        "date,product,sales,expenses,quantity\n"
        "2026-10-01,Product A,15000,9000,12\n"
        "2026-10-02,Product B,12000,7000,9"
    )
    with st.form("manual_entry"):
        manual_text = st.text_area("Manual data", value=manual_default, height=180)
        replace_manual = st.toggle("Replace the current workspace", value=False)
        submitted = st.form_submit_button("Add to workspace", type="primary")
    if submitted:
        try:
            manual_df = parse_manual_data(manual_text)
            manual_df["__source_file"] = "Manual entry"
            note = f"Manual entry added {len(manual_df):,} rows."
            if replace_manual or not has_data():
                set_workspace(manual_df, [note])
            else:
                from businesspilot.io_utils import combine_tables

                set_workspace(combine_tables([current_data(), manual_df]), list(st.session_state.source_notes) + [note])
            st.success(note)
            st.rerun()
        except Exception as exc:
            st.error(f"Could not parse manual data: {exc}")

if data_tabs[2].open:
    catalog = sample_catalog()
    sample_name = st.selectbox("Choose a sample", list(catalog.keys()))
    st.caption(catalog[sample_name])
    if st.button("Load sample into workspace", type="primary", icon=":material/dataset:"):
        frame = load_sample(sample_name)
        set_workspace(frame, [f"Loaded sample dataset: {sample_name}."], sample_name=sample_name)
        st.success(f"Loaded {len(frame):,} rows.")
        st.rerun()

if data_tabs[3].open:
    if not has_data():
        st.info("Load data before cleaning.", icon=":material/info:")
    else:
        with st.form("clean_form"):
            drop_dups = st.checkbox("Drop duplicate rows")
            drop_empty = st.checkbox("Drop fully empty rows")
            fill_numeric = st.selectbox("Missing numeric cells", ["Leave missing", "Fill with zero", "Fill with median"])
            applied = st.form_submit_button("Apply cleaning", type="primary")
        if applied:
            cleaned, notes = clean_frame(
                current_data(),
                drop_duplicates=drop_dups,
                drop_empty_rows=drop_empty,
                fill_numeric=fill_numeric,
            )
            set_workspace(cleaned, list(st.session_state.source_notes) + notes, preserve_roles=True)
            for note in notes:
                st.success(note)
            st.rerun()

data = current_data()
if data.empty:
    st.info("Upload a supported file, paste CSV, or load a sample to start.", icon=":material/info:")
    st.stop()

profile = profile_data(data)
st.subheader("Workspace preview")
k1, k2, k3, k4 = st.columns(4)
k1.metric("Rows", f"{profile['rows']:,}", border=True)
k2.metric("Columns", f"{profile['columns']:,}", border=True)
k3.metric("Duplicate rows", f"{profile['duplicate_rows']:,}", border=True)
k4.metric("Quality score", f"{profile['quality_score']}/100", border=True)

for warning in profile["warnings"]:
    st.warning(warning, icon=":material/warning:")
for note in st.session_state.source_notes[-6:]:
    st.caption(note)

st.dataframe(data.head(200), alt="First 200 rows of the current workspace", height=360)

st.subheader("Column mapping")
st.caption("Mapping tells the dashboard which fields are dates, money, products, and outcomes. Unmapped numeric columns are still summarised.")
current_roles = dict(st.session_state.column_roles or infer_column_roles(data))
options = ["— not mapped —"] + [str(c) for c in data.columns if not str(c).startswith("__")]
mapped = {}
cols = st.columns(2)
for i, (role, label) in enumerate(ROLE_LABELS.items()):
    with cols[i % 2]:
        current = current_roles.get(role) if current_roles.get(role) in options else "— not mapped —"
        mapped[role] = st.selectbox(label, options, index=options.index(current) if current in options else 0, help=ROLE_HELP[role], key=f"map_{role}")
if st.button("Save mapping", icon=":material/save:"):
    st.session_state.column_roles = {k: (None if v == "— not mapped —" else v) for k, v in mapped.items()}
    st.success("Column mapping saved.")

st.subheader("Column profile")
st.dataframe(column_summary(data), alt="Column types, missing values, and numeric ranges", height=320)

if st.button("Clear workspace", icon=":material/delete:"):
    set_workspace(data.iloc[0:0], [])
    st.rerun()
