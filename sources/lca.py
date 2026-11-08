"""DOL LCA disclosure data (H-1B, H-1B1, E-3 labor condition applications). Owner: A.

Built by build/clean_lca.py from the DOL quarterly files into data/clean/lca.parquet.
"""

from sources.base import SqlSource, data_path

SOURCE = SqlSource(
    name="lca",
    description=(
        "DOL LCA disclosure data, FY2020 to FY2026 Q3: every H-1B labor condition application with "
        "employer, SOC job code, job title, worksite city and state, offered wage, prevailing wage "
        "level, case status and dates. Answers: who files H-1B for which jobs, where, at what pay, "
        "and how that changed by year. Cannot answer: whether the petition was approved by USCIS, "
        "lottery odds, or green cards."
    ),
    tables={"lca": data_path("lca.parquet")},
    schema_doc="""Table lca: one row per LCA case, FY2020 to FY2026 Q3 (3.75 million cases, 97.5% H-1B).
- case_number: unique id
- case_status: 'Certified' | 'Certified - Withdrawn' | 'Withdrawn' | 'Denied'.
  An LCA is filed BEFORE the H-1B petition; Certified does not mean USCIS approved the visa.
  For "how many H-1B jobs did X file" count case_status IN ('Certified', 'Certified - Withdrawn').
- visa_class: 'H-1B' | 'H-1B1 Chile' | 'H-1B1 Singapore' | 'E-3 Australian'. Filter visa_class = 'H-1B' for H-1B questions.
- fiscal_year (int, Oct-Sep: FY2025 = Oct 2024 to Sep 2025, by decision date), calendar_year (int, of received_date)
- received_date, decision_date (DATE)
- employer_key: normalized employer name (lowercase, no LLC/INC). GROUP BY this, show employer_name via ANY_VALUE.
  Search companies with employer_key LIKE '%google%'.
- employer_name, employer_fein, employer_city, employer_state, naics_code (industry)
- soc_code: 'NN-NNNN' standard job code, e.g. 15-2051 Data Scientists, 15-1252 Software Developers,
  13-2011 Accountants and Auditors, 13-1161 Market Research Analysts, 15-2041 Statisticians,
  11-2021 Marketing Managers, 13-2051 Financial Analysts, 17-2141 Mechanical Engineers.
  Prefer soc_code over job_title: titles are free text ("Data Scientist II", "Sr. DS").
- soc_title, job_title
- full_time ('Y'/'N'), total_workers (positions on the case; one case can cover several workers)
- new_employment, continued_employment, change_employer: counts of workers by petition type
- worksite_city (Title Case, e.g. 'New York'), worksite_county, worksite_state (2-letter, e.g. 'NY'), worksite_postal_code
- wage_from_yearly, wage_to_yearly: offered wage in yearly USD (hourly x 2080 etc.). Use MEDIAN, not AVG.
- prevailing_wage_yearly, pw_wage_level ('I' to 'IV', I = entry level)
- h1b_dependent, willful_violator ('Yes'/'No'), source_file
Pitfalls:
- SOC codes changed in FY2023 (2018 SOC). 15-2051 Data Scientists barely exists before FY2023; earlier,
  data scientists were filed as 15-2041 Statisticians, 15-1111 Computer and Information Research
  Scientists, 15-1199 Computer Occupations All Other or 15-2031 Operations Research Analysts.
  For trends that start before FY2023, match job_title ILIKE '%data scientist%' as well as soc_code, and say so.
  Other occupations may have moved codes the same way; check soc_code counts by fiscal_year first.
- One company can file under several legal entities (amazon com services, amazon web services,
  amazon development center u s ...). Use employer_key LIKE 'amazon%' for "Amazon" and say which entities you included.
- FY2026 only covers Oct 2025 to Jun 2026 (Q1-Q3). One case = one application, not one hire.
- About 7% of rows have no pw_wage_level.""",
)
