"""Clean USCIS H-1B Employer Data Hub files into data/clean/uscis.parquet. Owner: B.

1. Put one file per fiscal year in data/raw/uscis/, named h1b_datahubexport-<year>.csv.
   Download them on your own computer: government sites often block cloud servers.
   - FY2009-FY2022: the archived "H-1B Employer Data Hub Files" page (comma-separated CSV).
   - FY2023 onwards: the Data Hub query tool -> Crosstab View -> filter one Fiscal Year ->
     Download -> CSV. These exports are UTF-16, tab-separated, and named
     "Employer Information.csv"; rename them. (The archived FY2023 file is incomplete.)
2. Run:  python -m build.clean_uscis                  (all files in data/raw/uscis/)
         python -m build.clean_uscis --min-year 2019  (drop older fiscal years)

Rows keep the hub's own grain: one row per fiscal year x employer x tax id x NAICS x location.
A large employer has many rows a year (one per office / tax id), so always SUM the counts.

Two layouts:
- Legacy (FY2009-FY2022): 4 counts, Initial / Continuing x Approvals / Denials. Headers went
  singular in FY2020; counts over 999 have a thousands comma.
- New (FY2023+): 6 petition types x Approval / Denial. Mapped back to the legacy split so
  trends run 2009-2026: initial = New Employment, continuing = the other 5 types. The 6-way
  breakdown is kept too (empty before FY2023).
"""

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

from build.common import normalize_employer, write_clean

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "uscis"

# output column -> names it has had in different years' files (first match wins)
COLUMNS = {
    "fiscal_year": ["FISCAL YEAR"],
    "employer_name": ["EMPLOYER", "EMPLOYER (PETITIONER) NAME"],
    "initial_approvals": ["INITIAL APPROVALS", "INITIAL APPROVAL"],
    "initial_denials": ["INITIAL DENIALS", "INITIAL DENIAL"],
    "continuing_approvals": ["CONTINUING APPROVALS", "CONTINUING APPROVAL"],
    "continuing_denials": ["CONTINUING DENIALS", "CONTINUING DENIAL"],
    "naics_code": ["NAICS", "INDUSTRY (NAICS) CODE"],
    "tax_id": ["TAX ID"],
    "state": ["STATE", "PETITIONER STATE"],
    "city": ["CITY", "PETITIONER CITY"],
    "zip": ["ZIP", "PETITIONER ZIP CODE"],
}
# FY2023+ petition types: output prefix -> header prefix in the file
PETITION_TYPES = {
    "new_employment": "NEW EMPLOYMENT",
    "continuation": "CONTINUATION",
    "change_same_employer": "CHANGE WITH SAME EMPLOYER",
    "new_concurrent": "NEW CONCURRENT",
    "change_of_employer": "CHANGE OF EMPLOYER",
    "amended": "AMENDED",
}
DETAIL = [f"{p}_{kind}" for p in PETITION_TYPES for kind in ("approvals", "denials")]
for _prefix, _header in PETITION_TYPES.items():
    COLUMNS[f"{_prefix}_approvals"] = [f"{_header} APPROVAL"]
    COLUMNS[f"{_prefix}_denials"] = [f"{_header} DENIAL"]

COUNTS = ["initial_approvals", "initial_denials", "continuing_approvals", "continuing_denials"]
REQUIRED = ["fiscal_year", "employer_name"]

# 2-digit NAICS sectors. Legacy files give the 2-digit code (31, 32, 33); new files give the
# sector range with its name ("31-33 - Manufacturing"). Both become the sector code below.
NAICS_SECTORS = {
    "11": "Agriculture, Forestry, Fishing and Hunting",
    "21": "Mining, Quarrying, and Oil and Gas Extraction",
    "22": "Utilities",
    "23": "Construction",
    "31-33": "Manufacturing",
    "42": "Wholesale Trade",
    "44-45": "Retail Trade",
    "48-49": "Transportation and Warehousing",
    "51": "Information",
    "52": "Finance and Insurance",
    "53": "Real Estate and Rental and Leasing",
    "54": "Professional, Scientific, and Technical Services",
    "55": "Management of Companies and Enterprises",
    "56": "Administrative and Support and Waste Management and Remediation Services",
    "61": "Educational Services",
    "62": "Health Care and Social Assistance",
    "71": "Arts, Entertainment, and Recreation",
    "72": "Accommodation and Food Services",
    "81": "Other Services (except Public Administration)",
    "92": "Public Administration",
}
_SECTOR_OF = {two: code for code in NAICS_SECTORS for two in
              ([str(n) for n in range(int(code[:2]), int(code[-2:]) + 1)] if "-" in code else [code])}

FILE_RE = re.compile(r"(\d{4})")


def to_count(values: pd.Series) -> pd.Series:
    """'1,476' / '3' / '' -> 1476 / 3 / 0."""
    cleaned = values.astype("string").str.replace(",", "", regex=False).str.strip()
    return pd.to_numeric(cleaned, errors="coerce").fillna(0).astype("Int64")


def to_sector(values: pd.Series) -> pd.Series:
    """'33' / '31-33 - Manufacturing' -> '31-33'; '99' / '' -> NA (unknown)."""
    code = values.astype("string").str.extract(r"^\s*(\d{2}(?:-\d{2})?)", expand=False)
    return code.map(lambda c: _SECTOR_OF.get(c, c if c in NAICS_SECTORS else pd.NA)
                    if isinstance(c, str) else pd.NA).astype("string")


def _read_raw(path: Path) -> pd.DataFrame:
    """Legacy files are UTF-8 comma CSV; Data Hub exports are UTF-16 tab-separated."""
    with open(path, "rb") as f:
        head = f.read(2)
    if head in (b"\xff\xfe", b"\xfe\xff"):
        return pd.read_csv(path, sep="\t", encoding="utf-16", dtype=str, keep_default_na=False)
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def read_one(path: Path) -> pd.DataFrame:
    """Read one hub file, keeping only our columns, renamed to our names."""
    raw = _read_raw(path)
    raw.columns = [re.sub(r"\s+", " ", str(c)).strip().upper() for c in raw.columns]

    out = pd.DataFrame(index=raw.index)
    for name, aliases in COLUMNS.items():
        found = next((a for a in aliases if a in raw.columns), None)
        out[name] = raw[found] if found else pd.NA
    missing = [c for c in REQUIRED if out[c].isna().all()]
    legacy = not out["initial_approvals"].isna().all()
    detailed = not out["new_employment_approvals"].isna().all()
    if missing or not (legacy or detailed):
        raise SystemExit(f"{path.name}: required columns not found. Columns were: {list(raw.columns)}")

    if detailed:  # FY2023+ layout: rebuild the legacy initial / continuing split
        for col in DETAIL:
            out[col] = to_count(out[col])
        for kind in ("approvals", "denials"):
            out[f"initial_{kind}"] = out[f"new_employment_{kind}"]
            out[f"continuing_{kind}"] = sum(out[f"{p}_{kind}"] for p in PETITION_TYPES if p != "new_employment")
    else:  # typed empty columns, so concat with new-layout years keeps Int64
        for col in DETAIL:
            out[col] = pd.array([pd.NA] * len(out), dtype="Int64")

    match = FILE_RE.search(path.stem)
    out["file_fy"] = int(match.group(1)) if match else pd.NA
    out["source_file"] = path.name
    print(f"  {path.name}: {len(out):,} rows ({'new 6-type' if detailed else 'legacy'} layout)", file=sys.stderr)
    return out


def clean(frames: list[pd.DataFrame], min_year: int | None = None) -> pd.DataFrame:
    df = pd.concat(frames, ignore_index=True)

    fy = pd.to_numeric(df["fiscal_year"].astype("string").str.strip(), errors="coerce")
    df["fiscal_year"] = fy.fillna(pd.to_numeric(df["file_fy"], errors="coerce")).astype("Int64")
    if min_year:
        df = df[df["fiscal_year"] >= min_year]

    df["employer_name"] = df["employer_name"].astype("string").str.strip()
    # A handful of rows per year have no employer name: nothing to look them up by.
    df = df[df["employer_name"].fillna("") != ""].copy()
    df["employer_key"] = df["employer_name"].map(normalize_employer)

    for col in COUNTS:
        df[col] = to_count(df[col])
    for col in DETAIL:  # stays NA for legacy years: the split is unknown, not zero
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    df["approvals"] = df["initial_approvals"] + df["continuing_approvals"]
    df["denials"] = df["initial_denials"] + df["continuing_denials"]

    def text(col):
        s = df[col].astype("string").str.strip()
        return s.mask(s == "")

    df["naics_code"] = to_sector(df["naics_code"])
    df["naics_title"] = df["naics_code"].map(NAICS_SECTORS).astype("string")
    df["tax_id"] = text("tax_id").str.zfill(4)  # last 4 digits only; text keeps leading zeros
    df["state"] = text("state").str.upper()
    df["city"] = text("city").str.title()  # Title Case, like lca.worksite_city
    df["zip"] = text("zip").str.extract(r"^(\d{5})", expand=False)

    keep = [
        "fiscal_year", "employer_key", "employer_name", "tax_id", "naics_code", "naics_title",
        "state", "city", "zip", *COUNTS, "approvals", "denials", *DETAIL, "source_file",
    ]
    return df[keep].sort_values(["fiscal_year", "employer_key"]).reset_index(drop=True)


def summarize(df: pd.DataFrame) -> None:
    print(f"\nrows: {len(df):,}  employers: {df['employer_key'].nunique():,}")
    by_year = df.groupby("fiscal_year")[COUNTS].sum()
    by_year["employers"] = df.groupby("fiscal_year")["employer_key"].nunique()
    print("totals per fiscal year:\n" + by_year.to_string())
    print(f"\nmissing state: {df['state'].isna().mean():.1%}  unknown NAICS: {df['naics_code'].isna().mean():.1%}")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="*", help="files to clean (default: every .csv in data/raw/uscis/)")
    parser.add_argument("--min-year", type=int, help="keep fiscal years >= this")
    args = parser.parse_args(argv)

    files = [Path(f).expanduser() for f in args.files] or sorted(RAW_DIR.glob("*.csv"))
    if not files:
        raise SystemExit(f"No USCIS files found. Put h1b_datahubexport-<year>.csv in {RAW_DIR}")

    print(f"reading {len(files)} files", file=sys.stderr)
    df = clean([read_one(f) for f in files], min_year=args.min_year)
    path = write_clean(df, "uscis")
    summarize(df)
    print(f"\nwrote {path} ({path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
