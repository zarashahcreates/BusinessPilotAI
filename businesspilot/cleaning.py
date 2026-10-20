from __future__ import annotations

import pandas as pd


def clean_frame(
    df: pd.DataFrame,
    *,
    drop_duplicates: bool = False,
    drop_empty_rows: bool = False,
    fill_numeric: str = "Leave missing",
) -> tuple[pd.DataFrame, list[str]]:
    work = df.copy()
    notes: list[str] = []
    before = len(work)

    if drop_empty_rows:
        work = work.dropna(how="all")
        notes.append(f"Removed {before - len(work):,} fully empty rows.")
        before = len(work)

    if drop_duplicates:
        work = work.drop_duplicates()
        notes.append(f"Removed {before - len(work):,} duplicate rows.")

    numeric_cols = []
    for col in work.columns:
        converted = pd.to_numeric(work[col], errors="coerce")
        if converted.notna().mean() >= 0.6:
            numeric_cols.append(col)

    if fill_numeric == "Fill with zero":
        for col in numeric_cols:
            work[col] = pd.to_numeric(work[col], errors="coerce").fillna(0)
        notes.append(f"Filled missing numeric cells with 0 in {len(numeric_cols)} columns.")
    elif fill_numeric == "Fill with median":
        for col in numeric_cols:
            numeric = pd.to_numeric(work[col], errors="coerce")
            work[col] = numeric.fillna(numeric.median())
        notes.append(f"Filled missing numeric cells with column medians in {len(numeric_cols)} columns.")

    if not notes:
        notes.append("No cleaning options were applied.")
    return work, notes
