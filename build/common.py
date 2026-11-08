"""Shared cleaning rules. Everyone's cleaning script uses these so the three sources join.

Join keys across LCA, USCIS and PERM:
    employer_key   normalize_employer(raw name)
    soc_code       normalize_soc(raw code)  -> "15-2051"
    fiscal_year    int, Oct-Sep (FY2025 = Oct 2024 - Sep 2025)
    calendar_year  int (LCA and PERM only; USCIS publishes fiscal years only)

Output: one parquet per source in data/clean/ (lca.parquet, uscis.parquet, perm.parquet),
lowercase snake_case column names.
TODO(B): extend the suffix list / add an alias table once real names are checked.
"""

import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd

CLEAN_DIR = Path(__file__).resolve().parent.parent / "data" / "clean"

_SUFFIXES = (
    "incorporated", "inc", "llc", "l l c", "llp", "lp", "ltd", "limited", "corp", "corporation",
    "co", "company", "plc", "pc", "pllc", "na", "n a", "usa", "us", "the",
)
_SUFFIX_RE = re.compile(r"(?:\s+(?:" + "|".join(re.escape(s) for s in _SUFFIXES) + r"))+$")


def normalize_employer(name) -> str:
    """'Google LLC' / 'GOOGLE, INC.' / 'google' -> 'google'."""
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return ""
    s = str(name).lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^the\s+", "", s)
    s = _SUFFIX_RE.sub("", s).strip()
    # "JPMorgan Chase & Co." -> "jpmorgan chase and" after the suffix goes: drop the dangling "and"
    return re.sub(r"\s+and$", "", s).strip()


def normalize_soc(code) -> str:
    """'15-2051.00' / '152051' / '15-2051' -> '15-2051'. Unknown shapes -> ''."""
    if code is None or (isinstance(code, float) and pd.isna(code)):
        return ""
    digits = re.sub(r"\D", "", str(code))[:6]
    return f"{digits[:2]}-{digits[2:]}" if len(digits) == 6 else ""


def fiscal_year(d) -> int | None:
    """US federal fiscal year: October starts the next FY."""
    if d is None or (isinstance(d, float) and pd.isna(d)):
        return None
    if isinstance(d, str):
        d = pd.to_datetime(d, errors="coerce")
        if pd.isna(d):
            return None
    if isinstance(d, (datetime, date, pd.Timestamp)):
        return d.year + 1 if d.month >= 10 else d.year
    return None


def write_clean(df: pd.DataFrame, name: str) -> Path:
    """Save one source's cleaned table as data/clean/<name>.parquet."""
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    df = df.rename(columns=lambda c: re.sub(r"\W+", "_", str(c).strip().lower()).strip("_"))
    path = CLEAN_DIR / f"{name}.parquet"
    df.to_parquet(path, index=False, compression="zstd")
    return path
