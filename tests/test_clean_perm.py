import pandas as pd

from build.clean_perm import clean, read_one

OLD_HEADER = ["CASE_NUMBER", "CASE_STATUS", "RECEIVED_DATE", "DECISION_DATE", "EMPLOYER_NAME", "EMPLOYER_CITY",
              "EMPLOYER_STATE_PROVINCE", "NAICS_CODE", "PW_SOC_CODE", "PW_SOC_TITLE", "PW_SKILL_LEVEL",
              "WAGE_OFFER_FROM", "WAGE_OFFER_TO", "WAGE_OFFER_UNIT_OF_PAY", "WORKSITE_CITY", "WORKSITE_STATE",
              "WORKSITE_POSTAL_CODE", "JOB_TITLE", "CLASS_OF_ADMISSION", "FOREIGN_WORKER_INFO_MAJOR"]
NEW_HEADER = ["CASE_NUMBER", "CASE_STATUS", "RECEIVED_DATE", "DECISION_DATE", "EMP_BUSINESS_NAME", "EMP_CITY",
              "EMP_STATE", "EMP_FEIN", "EMP_NAICS", "PWD_SOC_CODE", "PWD_SOC_TITLE", "JOB_TITLE",
              "JOB_OPP_WAGE_FROM", "JOB_OPP_WAGE_TO", "JOB_OPP_WAGE_PER", "PRIMARY_WORKSITE_CITY",
              "PRIMARY_WORKSITE_STATE", "PRIMARY_WORKSITE_POSTAL_CODE"]


def _csv(path, header, rows):
    pd.DataFrame(rows, columns=header).to_csv(path, index=False)
    return path


def test_old_and_new_layouts_land_in_one_schema(tmp_path):
    old = _csv(tmp_path / "PERM_Disclosure_Data_FY2023_Q4.csv", OLD_HEADER, [
        ["A-1", "Certified-Expired", "2022-03-01", "2023-01-15", "Google LLC", "MOUNTAIN VIEW", "CA", "541511",
         "15-1132", "SOFTWARE DEVELOPERS, APPLICATIONS", "Level II", "150000", "", "Year", "New York", "NEW YORK",
         "10011", "Software Engineer", "H-1B", "Computer Science"],
    ])
    new = _csv(tmp_path / "PERM_Disclosure_Data_FY2025_Q4.csv", NEW_HEADER, [
        ["G-100-1", "Certified - Expired", "2024-01-02", "2025-03-04", "GOOGLE, INC.", "MOUNTAIN VIEW", "CA",
         "77-0493581", "541511.0", "15-1252.00", "Software Developers", "SWE III", "80", "", "Hour",
         "New York", "NY", "10011.0"],
    ])
    df = clean([read_one(old), read_one(new)]).set_index("case_number")

    a, g = df.loc["A-1"], df.loc["G-100-1"]
    assert a.case_status == g.case_status == "Certified - Expired"
    assert a.employer_key == g.employer_key == "google"
    assert a.soc_code == "15-1132" and a.soc_code_2018 == g.soc_code_2018 == "15-1252"
    assert a.form_version == "old 9089" and g.form_version == "new 9089"
    assert a.fiscal_year == 2023 and g.fiscal_year == 2025 and a.calendar_year == 2022
    assert a.pw_wage_level == "II" and pd.isna(g.pw_wage_level)
    assert a.wage_from_yearly == 150000 and g.wage_from_yearly == 80 * 2080
    assert a.worksite_state == g.worksite_state == "NY" and g.worksite_postal_code == "10011"
    assert g.naics_code == "541511" and a.processing_days == 320
    assert a.class_of_admission == "H-1B" and a.foreign_worker_major == "COMPUTER SCIENCE"
    assert pd.isna(g.class_of_admission)  # not disclosed on the new form


def test_case_in_two_files_keeps_latest(tmp_path):
    row = ["A-9", "Certified", "2022-03-01", "2023-01-15", "Acme Inc", "X", "NY", "54", "15-2051", "DS",
           "Level I", "100000", "", "Year", "New York", "NY", "10001", "DS", "F-1", "STATS"]
    q2 = _csv(tmp_path / "PERM_Disclosure_Data_FY2023_Q2.csv", OLD_HEADER, [row[:1] + ["Denied"] + row[2:]])
    q4 = _csv(tmp_path / "PERM_Disclosure_Data_FY2023_Q4.csv", OLD_HEADER, [row])
    df = clean([read_one(q4), read_one(q2)])
    assert df["case_status"].tolist() == ["Certified"]
