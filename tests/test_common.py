from datetime import date

from build.common import fiscal_year, normalize_employer, normalize_soc


def test_normalize_employer_merges_spellings():
    assert normalize_employer("Google LLC") == "google"
    assert normalize_employer("GOOGLE, INC.") == "google"
    assert normalize_employer("Acme Analytics, L.L.C.") == "acme analytics"
    assert normalize_employer("The Goldman Sachs Group, Inc.") == "goldman sachs group"
    assert normalize_employer(None) == ""


def test_normalize_soc():
    assert normalize_soc("15-2051.00") == "15-2051"
    assert normalize_soc("152051") == "15-2051"
    assert normalize_soc("n/a") == ""


def test_fiscal_year_starts_in_october():
    assert fiscal_year(date(2024, 10, 1)) == 2025
    assert fiscal_year(date(2025, 9, 30)) == 2025
    assert fiscal_year("2025-03-11") == 2025
    assert fiscal_year("not a date") is None
