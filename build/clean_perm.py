"""Clean DOL PERM disclosure files into data/clean/perm.parquet. Owner: B.

1. Download the yearly files from https://www.dol.gov/agencies/eta/foreign-labor/performance
   (PERM Program: PERM_Disclosure_Data_FY<year>[_Q<n>].xlsx) into data/raw/perm/.
   Download them on your own computer: dol.gov blocks cloud servers.
2. Run:  python -m build.clean_perm            (all files in data/raw/perm/)

One row per PERM case. Two layouts, picked per column so any file works:
- Old ETA-9089 (FY2020-FY2024 files, case numbers A-...): has the worker's visa class at filing
  (CLASS_OF_ADMISSION), education, major, school and citizenship.
- New ETA-9089 (FY2025+ files, case numbers G-...): employer/job/wage/worksite only; the worker
  fields above are not disclosed.
Wages are converted to yearly dollars. Cases in more than one file keep the latest file's version.
"""

import argparse
import re
import sys
import time
from pathlib import Path

import pandas as pd

from build.clean_lca import to_yearly
from build.common import fiscal_year, normalize_employer, normalize_soc, soc_2018, state_code, write_clean

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "perm"

# output column -> names it has had (old 9089 names first, then new 9089 names)
COLUMNS = {
    "case_number": ["CASE_NUMBER"],
    "case_status": ["CASE_STATUS"],
    "received_date": ["RECEIVED_DATE"],
    "decision_date": ["DECISION_DATE"],
    "employer_name": ["EMPLOYER_NAME", "EMP_BUSINESS_NAME"],
    "employer_fein": ["EMPLOYER_FEIN", "EMP_FEIN"],
    "employer_city": ["EMPLOYER_CITY", "EMP_CITY"],
    "employer_state": ["EMPLOYER_STATE_PROVINCE", "EMP_STATE"],
    "naics_code": ["NAICS_CODE", "EMP_NAICS"],
    "employer_num_employees": ["EMPLOYER_NUM_EMPLOYEES", "EMP_NUM_PAYROLL"],
    "soc_code": ["PW_SOC_CODE", "PWD_SOC_CODE"],
    "soc_title": ["PW_SOC_TITLE", "PWD_SOC_TITLE"],
    "pw_wage_level": ["PW_SKILL_LEVEL"],
    "job_title": ["JOB_TITLE"],
    "wage_from": ["WAGE_OFFER_FROM", "JOB_OPP_WAGE_FROM"],
    "wage_to": ["WAGE_OFFER_TO", "JOB_OPP_WAGE_TO"],
    "wage_unit": ["WAGE_OFFER_UNIT_OF_PAY", "JOB_OPP_WAGE_PER"],
    "worksite_city": ["WORKSITE_CITY", "PRIMARY_WORKSITE_CITY"],
    "worksite_state": ["WORKSITE_STATE", "PRIMARY_WORKSITE_STATE"],
    "worksite_postal_code": ["WORKSITE_POSTAL_CODE", "PRIMARY_WORKSITE_POSTAL_CODE"],
    "minimum_education": ["MINIMUM_EDUCATION"],
    "class_of_admission": ["CLASS_OF_ADMISSION"],
    "country_of_citizenship": ["COUNTRY_OF_CITIZENSHIP"],
    "foreign_worker_education": ["FOREIGN_WORKER_EDUCATION"],
    "foreign_worker_major": ["FOREIGN_WORKER_INFO_MAJOR"],
    "foreign_worker_institution": ["FOREIGN_WORKER_INST_OF_ED"],
}
REQUIRED = ["case_number", "case_status", "employer_name", "soc_code", "wage_from", "wage_unit"]

FILE_RE = re.compile(r"FY(\d{4})(?:_?Q(\d))?", re.IGNORECASE)
STATUS = {"certified": "Certified", "certified-expired": "Certified - Expired",
          "denied": "Denied", "withdrawn": "Withdrawn"}


def read_one(path: Path) -> pd.DataFrame:
    """Read one disclosure file (first sheet), keeping only our columns, renamed to our names."""
    wanted = {alias for aliases in COLUMNS.values() for alias in aliases}
    t = time.time()
    if path.suffix.lower() == ".csv":
        raw = pd.read_csv(path, dtype=str, usecols=lambda c: c.strip().upper() in wanted)
    else:  # sheet 0: the FY2020 file has a stray second sheet of case numbers
        raw = pd.read_excel(path, sheet_name=0, dtype=str, engine="calamine",
                            usecols=lambda c: str(c).strip().upper() in wanted)
    raw.columns = [str(c).strip().upper() for c in raw.columns]

    out = pd.DataFrame(index=raw.index)
    for name, aliases in COLUMNS.items():
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
    form = "new" if "EMP_BUSINESS_NAME" in raw.columns else "old"
    print(f"  {path.name}: {len(out):,} rows, {form} ETA-9089 layout, {time.time() - t:.0f}s", file=sys.stderr)
    return out


def _digits(s: pd.Series, n: int | None = None) -> pd.Series:
    """'28255.0' -> '28255'; '541511' -> '541511'. Excel turns codes into floats."""
    s = s.astype("string").str.strip().str.replace(r"\.0+$", "", regex=True)
    if n:
        s = s.str.extract(rf"^(\d{{{n}}})", expand=False)
    return s.mask(s == "")


def clean(frames: list[pd.DataFrame]) -> pd.DataFrame:
    df = pd.concat(frames, ignore_index=True)

    # Same case in several files: keep the one from the latest file.
    df = df.sort_values(["file_fy", "file_quarter"]).drop_duplicates("case_number", keep="last")
    df["form_version"] = df["case_number"].astype("string").str.startswith("A-").map(
        {True: "old 9089", False: "new 9089"})

    status = df["case_status"].astype("string").str.strip().str.lower().str.replace(r"\s*-\s*", "-", regex=True)
    df["case_status"] = status.map(STATUS).fillna(df["case_status"].astype("string").str.strip().str.title())

    df["employer_name"] = df["employer_name"].astype("string").str.strip()
    df["employer_key"] = df["employer_name"].map(normalize_employer)
    df["soc_code"] = df["soc_code"].map(normalize_soc)
    df["soc_code_2018"] = df["soc_code"].map(soc_2018)
    df["soc_title"] = df["soc_title"].astype("string").str.strip().str.title()
    df["job_title"] = df["job_title"].astype("string").str.strip()
    df["pw_wage_level"] = df["pw_wage_level"].astype("string").str.strip().str.replace(r"(?i)^level\s+", "", regex=True)
    df["naics_code"] = _digits(df["naics_code"])
    df["employer_num_employees"] = pd.to_numeric(_digits(df["employer_num_employees"]), errors="coerce").astype("Int64")

    for col in ["employer_state", "worksite_state"]:  # old form: 'WASHINGTON', new form: 'WA'
        df[col] = state_code(df[col])
    for col in ["employer_city", "worksite_city"]:
        df[col] = df[col].astype("string").str.strip().str.title()
    df["worksite_postal_code"] = _digits(df["worksite_postal_code"], 5)
    for col in ["minimum_education", "class_of_admission", "country_of_citizenship",
                "foreign_worker_education", "foreign_worker_major", "foreign_worker_institution"]:
        s = df[col].astype("string").str.strip()
        df[col] = s.mask(s == "")
    df["country_of_citizenship"] = df["country_of_citizenship"].str.upper()
    df["foreign_worker_major"] = df["foreign_worker_major"].str.upper()
    df["foreign_worker_institution"] = df["foreign_worker_institution"].str.upper()

    for col in ["received_date", "decision_date"]:
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
    # The FY a case belongs to = the FY of the file it was published in (DOL groups by decision date).
    df["fiscal_year"] = df["file_fy"].fillna(df["decision_date"].map(fiscal_year)).astype("Int64")
    df["calendar_year"] = pd.to_datetime(df["received_date"], errors="coerce").dt.year.astype("Int64")
    df["processing_days"] = (pd.to_datetime(df["decision_date"]) - pd.to_datetime(df["received_date"])).dt.days.astype("Int64")

    df["wage_from_yearly"] = to_yearly(df["wage_from"], df["wage_unit"])
    df["wage_to_yearly"] = to_yearly(df["wage_to"], df["wage_unit"])
    # Obvious typos (e.g. an hourly wage marked as yearly) would wreck medians.
    df.loc[(df["wage_from_yearly"] < 15_000) | (df["wage_from_yearly"] > 2_000_000), "wage_from_yearly"] = pd.NA

    keep = [
        "case_number", "case_status", "form_version", "fiscal_year", "calendar_year",
        "received_date", "decision_date", "processing_days",
        "employer_key", "employer_name", "employer_fein", "employer_city", "employer_state",
        "naics_code", "employer_num_employees",
        "soc_code", "soc_code_2018", "soc_title", "job_title", "pw_wage_level",
        "worksite_city", "worksite_state", "worksite_postal_code",
        "wage_from_yearly", "wage_to_yearly",
        "minimum_education", "class_of_admission", "country_of_citizenship",
        "foreign_worker_education", "foreign_worker_major", "foreign_worker_institution", "source_file",
    ]
    return df[keep].reset_index(drop=True)


def summarize(df: pd.DataFrame) -> None:
    print(f"\nrows: {len(df):,}  employers: {df['employer_key'].nunique():,}")
    print("cases per fiscal year x form:\n" + pd.crosstab(df["fiscal_year"], df["form_version"]).to_string())
    print("\ncase_status:\n" + df["case_status"].value_counts().to_string())
    print(f"\nmissing SOC code: {(df['soc_code'] == '').mean():.1%}  "
          f"missing yearly wage: {df['wage_from_yearly'].isna().mean():.1%}")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="*", help="files to clean (default: every .xlsx/.csv in data/raw/perm/)")
    args = parser.parse_args(argv)

    files = [Path(f).expanduser() for f in args.files] or sorted(
        p for p in RAW_DIR.glob("*") if p.suffix.lower() in (".xlsx", ".csv") and "perm" in p.name.lower()
        and not p.name.startswith("~$"))
    if not files:
        raise SystemExit(f"No PERM files found. Put PERM_Disclosure_Data_FY*.xlsx in {RAW_DIR}")

    print(f"reading {len(files)} files", file=sys.stderr)
    df = clean([read_one(f) for f in files])
    path = write_clean(df, "perm")
    summarize(df)
    print(f"\nwrote {path} ({path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
