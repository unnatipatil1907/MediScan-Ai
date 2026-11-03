from __future__ import annotations

import csv
import io

import numpy as np
import pandas as pd

REQUIRED = ["test", "value", "unit", "min", "max"]


def validate_and_analyze(source_df: pd.DataFrame) -> pd.DataFrame:
    """Validate supplied lab-result rows and classify only against their supplied ranges."""
    if source_df is None or source_df.empty:
        raise ValueError("The file has no data rows.")

    df = source_df.copy()
    normalized = [str(c).strip().lstrip("\ufeff").lower() for c in df.columns]
    if any(not c for c in normalized):
        raise ValueError("The CSV contains a blank column header. Give every column a name.")
    if len(set(normalized)) != len(normalized):
        duplicates = sorted({c for c in normalized if normalized.count(c) > 1})
        raise ValueError("The CSV contains duplicate column headers: " + ", ".join(duplicates) + ". Rename them so each header is unique.")
    df.columns = normalized

    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError("Missing required column(s): " + ", ".join(missing) + ". Required headers: test,value,unit,min,max.")

    df = df[REQUIRED].copy()
    df["test"] = df["test"].fillna("").astype(str).str.strip()
    df["unit"] = df["unit"].fillna("").astype(str).str.strip()

    blank_test = df["test"].eq("")
    if blank_test.any():
        rows = (df.index[blank_test] + 2).tolist()
        raise ValueError(f"Missing test name on CSV row(s): {rows}.")

    blank_unit = df["unit"].eq("")
    if blank_unit.any():
        rows = (df.index[blank_unit] + 2).tolist()
        raise ValueError(f"Missing unit on CSV row(s): {rows}.")

    for col in ("value", "min", "max"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
        vals = df[col].to_numpy(dtype=float)
        bad = ~np.isfinite(vals)
        if bad.any():
            rows = (df.index[bad] + 2).tolist()
            raise ValueError(f"Column '{col}' has missing or non-numeric/invalid values on CSV row(s): {rows}.")

    invalid_range = df["min"] > df["max"]
    if invalid_range.any():
        rows = (df.index[invalid_range] + 2).tolist()
        raise ValueError(f"Minimum exceeds maximum on CSV row(s): {rows}.")

    df["status"] = "In range"
    df.loc[df["value"] < df["min"], "status"] = "Low"
    df.loc[df["value"] > df["max"], "status"] = "High"

    def flag(row):
        supplied = f"{row['min']:g}–{row['max']:g} {row['unit']}".strip()
        if row["status"] == "Low":
            return f"Below the supplied reference range ({supplied}); review with a qualified professional."
        if row["status"] == "High":
            return f"Above the supplied reference range ({supplied}); review with a qualified professional."
        return f"Within the supplied reference range ({supplied}); this does not rule out health concerns."

    df["review_flag"] = df.apply(flag, axis=1)
    return df[REQUIRED + ["status", "review_flag"]]


def make_summary(df: pd.DataFrame) -> str:
    low = int((df.status == "Low").sum())
    normal = int((df.status == "In range").sum())
    high = int((df.status == "High").sum())
    parts = [
        f"Compared {len(df)} result(s) with the minimum and maximum reference ranges supplied in the file.",
        f"Status counts: {low} low, {normal} in range, {high} high.",
    ]
    flagged = df[df.status != "In range"]
    if len(flagged):
        parts.append("Flagged values: " + "; ".join(
            f"{r.test}: {r.value:g} {r.unit} ({r.status.lower()}; supplied range {r['min']:g}–{r['max']:g} {r.unit})"
            for _, r in flagged.iterrows()) + ".")
    else:
        parts.append("All listed values are within the supplied reference ranges.")
    parts.append("These are range comparisons, not diagnoses. Laboratory ranges and interpretation depend on the laboratory and individual context.")
    return "\n\n".join(parts)


def read_csv_bytes(data: bytes) -> pd.DataFrame:
    """Read CSV while rejecting malformed records and duplicate raw headers."""
    if not data:
        raise ValueError("The uploaded CSV file is empty.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = data.decode("latin-1")
        except UnicodeDecodeError as exc:
            raise ValueError("Could not decode the CSV. Save it as UTF-8 and try again.") from exc

    try:
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        rows = list(reader)
    except csv.Error as exc:
        raise ValueError(f"Could not read the CSV because its quoting or row structure is malformed: {exc}") from exc

    if not rows or not rows[0] or all(not str(x).strip() for x in rows[0]):
        raise ValueError("The CSV is missing its header row.")
    header = [str(c).strip().lstrip("\ufeff").lower() for c in rows[0]]
    if any(not c for c in header):
        raise ValueError("The CSV contains a blank column header. Give every column a name.")
    if len(set(header)) != len(header):
        duplicates = sorted({c for c in header if header.count(c) > 1})
        raise ValueError("The CSV contains duplicate column headers: " + ", ".join(duplicates) + ". Rename them so each header is unique.")

    expected_width = len(rows[0])
    for row_number, row in enumerate(rows[1:], start=2):
        if not row or (len(row) == 1 and not row[0].strip()):
            continue
        if len(row) != expected_width:
            raise ValueError(f"Malformed CSV row {row_number}: expected {expected_width} fields but found {len(row)}.")

    try:
        df = pd.read_csv(io.StringIO(text), dtype=object, skip_blank_lines=True)
    except Exception as exc:
        raise ValueError(f"Could not read the CSV: {exc}") from exc
    return df


def compare_reports(previous: pd.DataFrame, current: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Compare saved report rows only where test names and units match unambiguously.

    This is a numerical comparison, not a medical trend interpretation. Reference
    ranges are kept alongside each result because ranges may differ between reports.
    """
    required = {"test", "value", "unit", "min", "max", "status"}
    if previous is None or current is None or not required.issubset(previous.columns) or not required.issubset(current.columns):
        raise ValueError("Both reports must contain test, value, unit, min, max, and status columns.")

    def prepare(frame: pd.DataFrame, prefix: str) -> tuple[pd.DataFrame, list[str]]:
        work = frame.copy()
        work["_key"] = work["test"].astype(str).str.strip().str.casefold() + "||" + work["unit"].astype(str).str.strip().str.casefold()
        counts = work["_key"].value_counts()
        ambiguous = set(counts[counts > 1].index)
        notes = [str(work.loc[work["_key"] == key, "test"].iloc[0]) for key in ambiguous]
        work = work[~work["_key"].isin(ambiguous)].copy()
        work = work.rename(columns={c: f"{prefix}_{c}" for c in ("test", "value", "unit", "min", "max", "status")})
        return work, notes

    old, old_ambiguous = prepare(previous, "previous")
    new, new_ambiguous = prepare(current, "current")
    merged = old.merge(new, left_on="_key", right_on="_key", how="inner")
    if merged.empty:
        return pd.DataFrame(columns=["test", "unit", "previous_value", "previous_status", "current_value", "current_status", "change", "previous_range", "current_range"]), sorted(set(old_ambiguous + new_ambiguous))
    result = pd.DataFrame({
        "test": merged["current_test"],
        "unit": merged["current_unit"],
        "previous_value": merged["previous_value"],
        "previous_status": merged["previous_status"],
        "current_value": merged["current_value"],
        "current_status": merged["current_status"],
        "change": merged["current_value"].astype(float) - merged["previous_value"].astype(float),
        "previous_range": merged.apply(lambda r: f"{r['previous_min']:g}–{r['previous_max']:g}", axis=1),
        "current_range": merged.apply(lambda r: f"{r['current_min']:g}–{r['current_max']:g}", axis=1),
    })
    return result.sort_values("test", key=lambda col: col.str.casefold()).reset_index(drop=True), sorted(set(old_ambiguous + new_ambiguous))
