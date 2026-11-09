"""DOL PERM disclosure data (green card labor certifications). Owner: B.

Built by build/clean_perm.py from the DOL yearly files into data/clean/perm.parquet.
"""

from sources.base import SqlSource, data_path

SOURCE = SqlSource(
    name="perm",
    description=(
        "DOL PERM disclosure data, FY2020 to FY2026 Q3: green card labor certification cases (the "
        "first step of employer-sponsored green cards) with employer, SOC job code, job title, "
        "worksite, offered wage, case status, dates and processing time. For FY2020-FY2024 also the "
        "worker's visa at filing (H-1B, F-1, L-1...), education, major, university and citizenship. "
        "Answers: which employers sponsor green cards for which jobs and where, at what pay, how "
        "often they are certified, how long DOL takes, and how many sponsored workers were on H-1B. "
        "Cannot answer: later I-140/I-485 outcomes, priority-date or visa-bulletin waits, H-1B "
        "approvals, or anything about a specific person."
    ),
    tables={"perm": data_path("perm.parquet")},
    schema_doc="""Table perm: one row per PERM case, FY2020 to FY2026 Q3 (774k cases).
PERM = the DOL labor certification an employer gets before filing a green card (I-140) for a worker.
- case_number: unique id. 'A-...' = old ETA-9089 form, 'G-...' = new form (see form_version).
- case_status: 'Certified' | 'Certified - Expired' | 'Denied' | 'Withdrawn'.
  'Certified - Expired' is still an approved case (the certification's 180-day window has passed),
  so for "did the employer sponsor / get certified" use case_status IN ('Certified', 'Certified - Expired').
  Certification rate = certified / (certified + Denied); Withdrawn cases are the employer's choice.
- form_version: 'old 9089' (all FY2020-FY2024 cases) | 'new 9089' (all FY2025+ cases).
- fiscal_year (int, Oct-Sep: FY2025 = Oct 2024 to Sep 2025, by decision date), calendar_year (int, of received_date)
- received_date, decision_date (DATE); processing_days = decision - received (use MEDIAN).
- employer_key: normalized employer name (lowercase, no LLC/INC), shared with lca and uscis.
  GROUP BY this, show employer_name via ANY_VALUE. Search with LIKE, % between words:
  employer_key LIKE '%ernst%young%', LIKE 'amazon%'.
- employer_name, employer_fein ('94-1687665'; FY2024+ only), employer_city, employer_state,
  naics_code (6-digit text, e.g. '541511' custom software, '522110' banking; first 2 digits = sector),
  employer_num_employees
- soc_code: 'NN-NNNN' as filed. FY2020-FY2024 cases mostly use 2010 SOC codes (15-1132/15-1133
  Software Developers, 15-1121 Computer Systems Analysts, 15-1199 Computer Occupations All Other),
  FY2025+ use 2018 codes (15-1252 Software Developers, 15-2051 Data Scientists).
- soc_code_2018: soc_code converted to 2018 SOC where the code simply moved. USE THIS for jobs and
  trends across years: 15-1252 Software Developers, 15-1211 Computer Systems Analysts,
  15-1221 Computer and Information Research Scientists, 15-1212 Information Security Analysts,
  15-2051 Data Scientists, 15-2041 Statisticians, 13-2011 Accountants and Auditors,
  13-2051 Financial Analysts, 13-1161 Market Research Analysts, 11-2021 Marketing Managers,
  17-2141 Mechanical Engineers, 17-2072 Electronics Engineers.
- soc_title, job_title (free text: prefer soc_code_2018)
- pw_wage_level: 'I' to 'IV' (I = entry). FY2020-FY2024 only (NULL from FY2025).
- worksite_city (Title Case, e.g. 'New York'), worksite_state (2-letter, 'NY'), worksite_postal_code
- wage_from_yearly, wage_to_yearly: offered wage in yearly USD (hourly x 2080 etc.). Use MEDIAN, not AVG.
- FY2020-FY2024 only (NULL from FY2025, the new form does not disclose them):
  class_of_admission: the worker's visa when the case was filed: 'H-1B' (~70%), 'F-1' (students, ~8%),
    'L-1', 'TN', 'Not in USA', ... This is the "H-1B to green card" link.
  minimum_education (the job's requirement), foreign_worker_education ("Master's", "Bachelor's",
  'Doctorate', ...), foreign_worker_major (uppercase, 'COMPUTER SCIENCE'),
  foreign_worker_institution (uppercase; one school has several spellings: Columbia is
  'COLUMBIA UNIVERSITY' and 'COLUMBIA UNIVERSITY IN THE CITY OF NEW YORK', so use
  LIKE 'COLUMBIA UNIVERSITY%' and exclude 'BRITISH COLUMBIA'), country_of_citizenship (uppercase, 'INDIA').
- source_file
Pitfalls:
- One case = one worker's application, not a hire, and certification is not a green card.
- FY2026 only covers Oct 2025 to Jun 2026 (Q1-Q3), and October 2025 has almost no decisions (21),
  so FY2026 totals are not comparable to full years. Recent years have fewer 'Certified - Expired'.
- Processing time rose from a median of ~140 days (FY2020) to ~490 days (FY2025-26): a case decided
  in FY2025 was usually filed in calendar 2023 or 2024.
- Top filers by count include food processors and farms (non-professional jobs). For questions
  from students, filter by soc_code_2018 or exclude low-wage occupations.
- One company files under several employer_keys, and keys can differ between years
  ('ernst young u s' vs 'ernst and young u s'; 'amazon com services', 'amazon web services',
  'amazon development center u s'). Use a prefix/LIKE match and say which entities you included.
- Visa, education, major, school and citizenship questions can only be answered for FY2020-FY2024;
  say so instead of returning zeros for FY2025+.""",
)
