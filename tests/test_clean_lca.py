import pandas as pd

from build.clean_lca import clean, to_yearly


def test_to_yearly_handles_units_and_money_strings():
    out = to_yearly(pd.Series(["150000", "$70.50", "9,000", "5", "1"]),
                    pd.Series(["Year", "Hour", "Month", "Week", "Fortnight"]))
    assert out.tolist()[:4] == [150000, 146640, 108000, 260]
    assert pd.isna(out.iloc[4])


def _frame(case, fy, q, **kw):
    row = {"case_number": case, "case_status": "certified", "received_date": "2024-11-04",
           "decision_date": "2024-11-11", "visa_class": "H-1B", "job_title": "DS", "soc_code": "15-2051.00",
           "soc_title": "DATA SCIENTISTS", "full_time": "Y", "total_workers": "1", "new_employment": None,
           "continued_employment": None, "change_employer": None, "employer_name": "Google LLC",
           "employer_fein": None, "employer_city": None, "employer_state": None, "naics_code": None,
           "worksite_city": "NEW YORK", "worksite_county": None, "worksite_state": "ny",
           "worksite_postal_code": None, "wage_from": "150000", "wage_to": None, "wage_unit": "Year",
           "prevailing_wage": "120000", "pw_unit": "Year", "pw_wage_level": "II", "h1b_dependent": None,
           "willful_violator": None, "source_file": f"FY{fy}_Q{q}", "file_fy": fy, "file_quarter": q}
    row.update(kw)
    return pd.DataFrame([row])


def test_clean_dedupes_to_latest_file_and_normalizes():
    df = clean([_frame("I-1", 2025, 2, case_status="withdrawn"), _frame("I-1", 2025, 1),
                _frame("I-2", 2025, 1, visa_class="E-3 Australian")], h1b_only=True)
    assert df["case_number"].tolist() == ["I-1"]
    row = df.iloc[0]
    assert row.case_status == "Withdrawn" and row.employer_key == "google" and row.soc_code == "15-2051"
    assert row.worksite_state == "NY" and row.worksite_city == "New York"
    assert row.fiscal_year == 2025 and row.calendar_year == 2024 and row.wage_from_yearly == 150000
