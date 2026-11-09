import pandas as pd

from build.clean_uscis import clean, read_one, to_count


def test_to_count_handles_thousands_commas_and_blanks():
    assert to_count(pd.Series(["1,476", "3", "", None])).tolist() == [1476, 3, 0, 0]


def test_read_one_maps_old_and_new_headers(tmp_path):
    old = tmp_path / "h1b_datahubexport-2019.csv"
    old.write_text('"Fiscal Year","Employer","Initial Approvals","Initial Denials","Continuing Approvals",'
                   '"Continuing Denials","NAICS","Tax ID","State","City","ZIP"\n'
                   '"2019","GOOGLE LLC","1,200","5","3,000","7","54","","CA","MOUNTAIN VIEW","94043"\n')
    new = tmp_path / "h1b_datahubexport-2020.csv"
    new.write_text('"Fiscal Year",Employer,"Initial Approval","Initial Denial","Continuing Approval",'
                   '"Continuing Denial",NAICS,"Tax ID",State,City,ZIP\n'
                   '2020,"Google LLC",10,1,20,2,54,0581,ca,mountain view,94043\n'
                   '2020,,1,0,0,0,71,3557,NY,ASTORIA,11106\n')
    df = clean([read_one(old), read_one(new)])

    assert len(df) == 2  # the row with no employer is dropped
    assert df["employer_key"].tolist() == ["google", "google"]
    assert df["fiscal_year"].tolist() == [2019, 2020]
    assert df["initial_approvals"].tolist() == [1200, 10]
    assert df["approvals"].tolist() == [4200, 30] and df["denials"].tolist() == [12, 3]
    new_row = df.iloc[1]
    assert new_row.tax_id == "0581" and new_row.state == "CA" and new_row.city == "Mountain View"
    assert pd.isna(df.iloc[0].tax_id)


NEW_HEADER = ["Line by line", "Fiscal Year   ", "Employer (Petitioner) Name", "Tax ID", "Industry (NAICS) Code",
              "Petitioner City", "Petitioner State", "Petitioner Zip Code",
              "New Employment Approval", "New Employment Denial", "Continuation Approval", "Continuation Denial",
              "Change with Same Employer Approval", "Change with Same Employer Denial",
              "New Concurrent Approval", "New Concurrent Denial", "Change of Employer Approval",
              "Change of Employer Denial", "Amended Approval", "Amended Denial"]


def test_read_one_handles_utf16_tab_export_with_six_petition_types(tmp_path):
    row = ["1", "2024", "GOOGLE LLC", "581", "54 - Professional, Scientific, and Technical Services",
           "MOUNTAIN VIEW", "CA", "94043", "1,000", "10", "200", "2", "30", "0", "4", "0", "50", "1", "6", "0"]
    path = tmp_path / "h1b_datahubexport-2024.csv"
    path.write_text("\t".join(NEW_HEADER) + "\n" + "\t".join(row) + "\n", encoding="utf-16")
    df = clean([read_one(path)])

    r = df.iloc[0]
    assert r.fiscal_year == 2024 and r.employer_key == "google" and r.tax_id == "0581"
    assert r.new_employment_approvals == 1000 and r.change_of_employer_approvals == 50
    assert r.initial_approvals == 1000 and r.initial_denials == 10
    assert r.continuing_approvals == 200 + 30 + 4 + 50 + 6 and r.continuing_denials == 3
    assert r.naics_code == "54" and r.naics_title.startswith("Professional")


def test_naics_sectors_match_across_layouts(tmp_path):
    old = tmp_path / "h1b_datahubexport-2019.csv"
    old.write_text('"Fiscal Year","Employer","Initial Approvals","Initial Denials","Continuing Approvals",'
                   '"Continuing Denials","NAICS","Tax ID","State","City","ZIP"\n'
                   '"2019","A","1","0","0","0","32","","NY","X","10001"\n'
                   '"2019","B","1","0","0","0","99","","NY","X","10001"\n')
    new = tmp_path / "h1b_datahubexport-2024.csv"
    row = ["1", "2024", "C", "1", "31-33 - Manufacturing", "X", "NY", "10001"] + ["0"] * 12
    new.write_text("\t".join(NEW_HEADER) + "\n" + "\t".join(row) + "\n", encoding="utf-16")
    df = clean([read_one(old), read_one(new)])

    assert df["naics_code"].tolist()[0] == "31-33" and pd.isna(df["naics_code"].tolist()[1])
    assert df["naics_code"].tolist()[2] == "31-33" and df["naics_title"].tolist()[2] == "Manufacturing"
    assert pd.isna(df.iloc[0].new_employment_approvals)  # legacy years have no 6-type split


def test_min_year_filter(tmp_path):
    f = tmp_path / "h1b_datahubexport-2015.csv"
    f.write_text('"Fiscal Year","Employer","Initial Approvals","Initial Denials","Continuing Approvals",'
                 '"Continuing Denials","NAICS","Tax ID","State","City","ZIP"\n'
                 '"2015","ACME INC","1","0","0","0","54","","NY","NEW YORK","10001"\n')
    assert clean([read_one(f)], min_year=2019).empty
