from datetime import date

from build.common import fiscal_year, normalize_employer, normalize_soc, soc_2018


def test_normalize_employer_merges_spellings():
    assert normalize_employer("Google LLC") == "google"
    assert normalize_employer("GOOGLE, INC.") == "google"
    assert normalize_employer("Acme Analytics, L.L.C.") == "acme analytics"
    assert normalize_employer("The Goldman Sachs Group, Inc.") == "goldman sachs group"
    assert normalize_employer("JPMorgan Chase & Co.") == "jpmorgan chase"
    assert normalize_employer("GOLDMAN SACHS & CO. LLC") == "goldman sachs"
    assert normalize_employer(None) == ""


def test_normalize_soc():
    assert normalize_soc("15-2051.00") == "15-2051"
    assert normalize_soc("152051") == "15-2051"
    assert normalize_soc("n/a") == ""


def test_soc_2018_maps_moved_codes_only():
    assert soc_2018("15-1132") == "15-1252" and soc_2018("15-1133") == "15-1252"
    assert soc_2018("15-1252") == "15-1252"  # already 2018
    assert soc_2018("15-1199") == "15-1199"  # split code: left alone
    assert soc_2018("") == ""


def test_fiscal_year_starts_in_october():
    assert fiscal_year(date(2024, 10, 1)) == 2025
    assert fiscal_year(date(2025, 9, 30)) == 2025
    assert fiscal_year("2025-03-11") == 2025
    assert fiscal_year("not a date") is None
