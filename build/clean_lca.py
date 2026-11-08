"""Clean DOL LCA disclosure files into data/clean/lca.parquet. Owner: A.

1. Download the quarterly files from https://www.dol.gov/agencies/eta/foreign-labor/performance
   (LCA Programs: LCA_Disclosure_Data_FY<year>_Q<n>.xlsx) into data/raw/lca/.
   Download them on your own computer: dol.gov blocks cloud servers.
2. Run:  uv run python -m build.clean_lca            (all files in data/raw/lca/)
         uv run python -m build.clean_lca --h1b-only  (drop H-1B1 and E-3)

One row per LCA case. Wages are converted to yearly dollars. Cases that show up
in more than one file keep the version from the latest file.
"""

import argparse
import re
import sys
import time
from pathlib import Path

import pandas as pd

from build.common import CLEAN_DIR, fiscal_year, normalize_employer, normalize_soc, write_clean

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "lca"

# output column -> names it has had in different years' files (first match wins)
COLUMNS = {
    "case_number": ["CASE_NUMBER"],
    "case_status": ["CASE_STATUS"],
    "received_date": ["RECEIVED_DATE", "CASE_SUBMITTED"],
    "decision_date": ["DECISION_DATE"],
    "visa_class": ["VISA_CLASS"],
    "job_title": ["JOB_TITLE"],
    "soc_code": ["SOC_CODE"],
    "soc_title": ["SOC_TITLE", "SOC_NAME"],
    "full_time": ["FULL_TIME_POSITION"],
    "total_workers": ["TOTAL_WORKER_POSITIONS", "TOTAL_WORKERS"],
    "new_employment": ["NEW_EMPLOYMENT"],
    "continued_employment": ["CONTINUED_EMPLOYMENT"],
    "change_employer": ["CHANGE_EMPLOYER"],
    "employer_name": ["EMPLOYER_NAME"],
    "employer_fein": ["EMPLOYER_FEIN"],
    "employer_city": ["EMPLOYER_CITY"],
    "employer_state": ["EMPLOYER_STATE"],
    "naics_code": ["NAICS_CODE"],
    "worksite_city": ["WORKSITE_CITY", "WORKSITE_CITY_1"],
    "worksite_county": ["WORKSITE_COUNTY", "WORKSITE_COUNTY_1"],
    "worksite_state": ["WORKSITE_STATE", "WORKSITE_STATE_1"],
    "worksite_postal_code": ["WORKSITE_POSTAL_CODE", "WORKSITE_POSTAL_CODE_1"],
    "wage_from": ["WAGE_RATE_OF_PAY_FROM", "WAGE_RATE_OF_PAY_FROM_1"],
    "wage_to": ["WAGE_RATE_OF_PAY_TO", "WAGE_RATE_OF_PAY_TO_1"],
    "wage_unit": ["WAGE_UNIT_OF_PAY", "WAGE_UNIT_OF_PAY_1"],
    "prevailing_wage": ["PREVAILING_WAGE", "PREVAILING_WAGE_1"],
    "pw_unit": ["PW_UNIT_OF_PAY", "PW_UNIT_OF_PAY_1"],
    "pw_wage_level": ["PW_WAGE_LEVEL", "PW_WAGE_LEVEL_1"],
    "h1b_dependent": ["H_1B_DEPENDENT", "H1B_DEPENDENT"],
    "willful_violator": ["WILLFUL_VIOLATOR"],
}
REQUIRED = ["case_number", "case_status", "employer_name", "soc_code", "wage_from", "wage_unit"]

YEARLY = {"year": 1, "month": 12, "bi-weekly": 26, "biweekly": 26, "week": 52, "hour": 2080}

FILE_RE = re.compile(r"FY(\d{4})(?:_Q(\d))?", re.IGNORECASE)


def to_yearly(amount: pd.Series, unit: pd.Series) -> pd.Series:
    """Convert a wage to yearly dollars (hour x 2080, week x 52, ...). Unknown unit -> NaN."""
    factor = unit.astype(str).str.strip().str.lower().map(YEARLY)
    values = pd.to_numeric(amount.astype(str).str.replace(r"[$,]", "", regex=True), errors="coerce")
    return (values * factor).round(0)


def read_one(path: Path) -> pd.DataFrame:
    """Read one disclosure file, keeping only the columns we use, renamed to our names."""
    wanted = {alias for aliases in COLUMNS.values() for alias in aliases}
    t = time.time()
    if path.suffix.lower() == ".csv":
        raw = pd.read_csv(path, dtype=str, usecols=lambda c: c.strip().upper() in wanted)
    else:
        raw = pd.read_excel(path, dtype=str, engine="openpyxl", usecols=lambda c: str(c).strip().upper() in wanted)
    raw.columns = [str(c).strip().upper() for c in raw.columns]

    out = pd.DataFrame(index=raw.index)
    for name, aliases in COLUMNS.items():
        # Coalesce: take the first non-empty value across the names this column has had.
        series = pd.Series(pd.NA, index=raw.index, dtype="object")
        for alias in aliases:
            if alias in raw.columns:
                series = series.where(series.notna(), raw[alias])
        out[name] = series
    missing = [c for c in REQUIRED if out[c].isna().all()]
    if missing:
        raise SystemExit(f"{path.name}: required columns not found: {missing}. Columns were: {list(raw.columns)}")

    match = FILE_RE.search(path.stem)
    out["source_file"] = path.name
    out["file_fy"] = int(match.group(1)) if match else pd.NA
    out["file_quarter"] = int(match.group(2)) if match and match.group(2) else 4
    print(f"  {path.name}: {len(out):,} rows in {time.time() - t:.0f}s", file=sys.stderr)
    return out


def clean(frames: list[pd.DataFrame], h1b_only: bool = False) -> pd.DataFrame:
    df = pd.concat(frames, ignore_index=True)

    # Same case in several files: keep the one from the latest file.
    df = df.sort_values(["file_fy", "file_quarter"]).drop_duplicates("case_number", keep="last")

    for col in ["case_status", "visa_class", "pw_wage_level", "full_time", "h1b_dependent", "willful_violator"]:
        df[col] = df[col].astype("string").str.strip()
    df["case_status"] = df["case_status"].str.title()
    df["worksite_state"] = df["worksite_state"].astype("string").str.strip().str.upper()
    df["worksite_city"] = df["worksite_city"].astype("string").str.strip().str.title()
    df["job_title"] = df["job_title"].astype("string").str.strip()
    if h1b_only:
        df = df[df["visa_class"].str.upper() == "H-1B"]

    df["employer_key"] = df["employer_name"].map(normalize_employer)
    df["soc_code"] = df["soc_code"].map(normalize_soc)
    df["soc_title"] = df["soc_title"].astype("string").str.strip().str.title()

    for col in ["received_date", "decision_date"]:
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
    # The FY a case belongs to = the FY of the file it was published in (DOL groups by decision date).
    df["fiscal_year"] = df["file_fy"].fillna(df["decision_date"].map(fiscal_year)).astype("Int64")
    df["calendar_year"] = pd.to_datetime(df["received_date"], errors="coerce").dt.year.astype("Int64")

    df["wage_from_yearly"] = to_yearly(df["wage_from"], df["wage_unit"])
    df["wage_to_yearly"] = to_yearly(df["wage_to"], df["wage_unit"])
    df["prevailing_wage_yearly"] = to_yearly(df["prevailing_wage"], df["pw_unit"])
    # Obvious typos (e.g. an hourly wage marked as yearly) would wreck medians.
    df.loc[(df["wage_from_yearly"] < 15_000) | (df["wage_from_yearly"] > 2_000_000), "wage_from_yearly"] = pd.NA
    df["total_workers"] = pd.to_numeric(df["total_workers"], errors="coerce").astype("Int64")

    keep = [
        "case_number", "case_status", "visa_class", "fiscal_year", "calendar_year", "received_date", "decision_date",
        "employer_key", "employer_name", "employer_fein", "employer_city", "employer_state", "naics_code",
        "soc_code", "soc_title", "job_title", "full_time", "total_workers",
        "new_employment", "continued_employment", "change_employer",
        "worksite_city", "worksite_county", "worksite_state", "worksite_postal_code",
        "wage_from_yearly", "wage_to_yearly", "prevailing_wage_yearly", "pw_wage_level",
        "h1b_dependent", "willful_violator", "source_file",
    ]
    return df[keep].reset_index(drop=True)


def summarize(df: pd.DataFrame) -> None:
    print(f"\nrows: {len(df):,}  employers: {df['employer_key'].nunique():,}")
    print("rows per fiscal year:\n" + df["fiscal_year"].value_counts().sort_index().to_string())
    print("\ncase_status:\n" + df["case_status"].value_counts().to_string())
    print(f"\nmissing SOC code: {(df['soc_code'] == '').mean():.1%}  "
          f"missing yearly wage: {df['wage_from_yearly'].isna().mean():.1%}")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="*", help="files to clean (default: every .xlsx/.csv in data/raw/lca/)")
    parser.add_argument("--h1b-only", action="store_true", help="drop H-1B1 and E-3 cases")
    args = parser.parse_args(argv)

    files = [Path(f).expanduser() for f in args.files] or sorted(
        p for p in RAW_DIR.glob("LCA_*") if p.suffix.lower() in (".xlsx", ".csv")
        # DOL misspells some file names (FY2026 is "LCA_Dislclosure_Data_..."), so match loosely
        and "data" in p.name.lower() and "appendix" not in p.name.lower() and "worksite" not in p.name.lower())
    if not files:
        raise SystemExit(f"No LCA files found. Put LCA_Disclosure_Data_FY*_Q*.xlsx in {RAW_DIR}")

    print(f"reading {len(files)} files", file=sys.stderr)
    df = clean([read_one(f) for f in files], h1b_only=args.h1b_only)
    path = write_clean(df, "lca")
    summarize(df)
    print(f"\nwrote {path} ({path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
