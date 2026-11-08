"""Quick check of a downloaded LCA disclosure file (run on your own computer).

    uv run python build/inspect_lca.py ~/Downloads/LCA_Disclosure_Data_FY2025_Q4.xlsx

Prints size, row count, columns, which of the columns we need are present,
and a few summary numbers. Paste the output back into the thread.
"""

import sys
import time
from pathlib import Path

import pandas as pd

NEEDED = [
    "CASE_NUMBER", "CASE_STATUS", "RECEIVED_DATE", "DECISION_DATE", "VISA_CLASS",
    "JOB_TITLE", "SOC_CODE", "SOC_TITLE", "FULL_TIME_POSITION",
    "EMPLOYER_NAME", "EMPLOYER_FEIN", "NAICS_CODE",
    "WORKSITE_CITY", "WORKSITE_STATE",
    "WAGE_RATE_OF_PAY_FROM", "WAGE_RATE_OF_PAY_TO", "WAGE_UNIT_OF_PAY",
    "PREVAILING_WAGE", "PW_WAGE_LEVEL",
]


def main(path: str) -> None:
    p = Path(path).expanduser()
    print(f"file: {p.name}  size: {p.stat().st_size / 1e6:.1f} MB")
    t = time.time()
    df = pd.read_excel(p, engine="openpyxl")
    print(f"rows: {len(df):,}  columns: {len(df.columns)}  read in {time.time() - t:.0f}s")
    cols = [str(c).strip().upper() for c in df.columns]
    df.columns = cols
    print("\nall columns:\n" + ", ".join(cols))
    missing = [c for c in NEEDED if c not in cols]
    print("\nneeded columns missing:", missing or "none")
    for c in ["CASE_STATUS", "VISA_CLASS", "WAGE_UNIT_OF_PAY", "PW_WAGE_LEVEL"]:
        if c in df:
            print(f"\n{c}:\n{df[c].value_counts(dropna=False).head(8).to_string()}")
    if "RECEIVED_DATE" in df:
        d = pd.to_datetime(df["RECEIVED_DATE"], errors="coerce")
        print(f"\nRECEIVED_DATE range: {d.min()} to {d.max()}")
    if "EMPLOYER_NAME" in df:
        print(f"\ndistinct employers: {df['EMPLOYER_NAME'].nunique():,}")
        print(df["EMPLOYER_NAME"].value_counts().head(10).to_string())


if __name__ == "__main__":
    main(sys.argv[1])
