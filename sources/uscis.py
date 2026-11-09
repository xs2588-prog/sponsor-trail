"""USCIS H-1B Employer Data Hub (approvals and denials per employer). Owner: B.

Built by build/clean_uscis.py from the yearly Data Hub files into data/clean/uscis.parquet.
"""

from sources.base import SqlSource, data_path

SOURCE = SqlSource(
    name="uscis",
    description=(
        "USCIS H-1B Employer Data Hub, FY2009 to FY2026 (full years): how many H-1B petitions USCIS "
        "approved and denied per employer and fiscal year, split into initial (new employment) and "
        "continuing (extensions, amendments, change of employer...), with industry (NAICS sector) and "
        "the employer's filing state and city. From FY2023 also by petition type (new employment, "
        "change of employer, amended, ...). Answers: did an employer's H-1B petitions actually get "
        "approved, approval and denial rates, and how volumes changed by year. Cannot answer: job "
        "titles, occupations or wages (no job data at all: find employers for a job in another source "
        "first), worksite location, calendar-year splits, lottery odds, or green cards."
    ),
    tables={"uscis": data_path("uscis.parquet")},
    schema_doc="""Table uscis: USCIS H-1B Employer Data Hub, FY2009 to FY2026 (1.05 million rows).
Grain: one row per fiscal_year x employer x tax_id x NAICS x filing location. A big employer has
several rows a year (up to ~40), so ALWAYS SUM the counts and GROUP BY employer_key.
Counts are USCIS's FIRST decision on each petition (not final outcomes after appeal), and count
petitions, not people.
- fiscal_year (int): US federal fiscal year of the decision, Oct-Sep (FY2025 = Oct 2024 to Sep 2025).
  There is no month or calendar year. FY2026 is complete (ends Sep 2026).
- employer_key: normalized employer name (lowercase, no LLC/INC/punctuation), shared with lca and perm.
  GROUP BY this, show employer_name via ANY_VALUE. Search with LIKE, putting % between words
  because spacing and "and" differ: employer_key LIKE '%ernst%young%', LIKE 'amazon%'.
- employer_name: name as USCIS printed it, uppercase, often abbreviated or misspelled
  ('BIBB MED CTR BIBB COUNTY HEALTH CA', 'AMAZON WEB SVCS').
- tax_id: last 4 digits of the employer's tax id, text like '0581'.
  Same company name with different tax_id = different legal entities.
- naics_code: industry sector, text: '54' (Professional, Scientific, and Technical Services),
  '51' (Information), '52' (Finance and Insurance), '62' (Health Care), '61' (Educational Services),
  '31-33' (Manufacturing), '44-45' (Retail Trade), '48-49' (Transportation). NULL = unknown (4.5%).
- naics_title: sector name, e.g. 'Finance and Insurance'.
- state: 2-letter state of the EMPLOYER's filing address, e.g. 'NY'. city: Title Case, e.g. 'New York'.
  zip: 5-digit text. This is NOT the worksite: Google's New York staff are filed under
  Mountain View, CA. For "jobs in New York" find employers by worksite in lca, then look them up
  here by employer_key WITHOUT a state filter.
- initial_approvals, initial_denials: petitions for new employment (a new H-1B worker,
  cap-subject lottery winners plus cap-exempt employers such as universities).
- continuing_approvals, continuing_denials: everything else: extensions, change with same
  employer, new concurrent, change of employer (transfers from another company), amended.
- approvals = initial_approvals + continuing_approvals; denials = initial_denials + continuing_denials.
- FY2023 onwards only (NULL before; NULL means not reported, not zero), each _approvals and _denials:
  new_employment_ (= initial), continuation_, change_same_employer_, new_concurrent_,
  change_of_employer_ (H-1B transfers into this employer), amended_.
- source_file: raw file name.
How to compute:
- Approval rate = SUM(approvals) / NULLIF(SUM(approvals) + SUM(denials), 0). Say whether it is
  initial-only or all petitions; initial is closer to "new hires". Ignore rates for employers
  with tiny totals (e.g. under 10 decisions) or flag them.
- Example: SELECT employer_key, ANY_VALUE(employer_name) AS name, SUM(initial_approvals) AS ia,
  SUM(initial_denials) AS id, ROUND(SUM(initial_approvals) / NULLIF(SUM(initial_approvals) +
  SUM(initial_denials), 0), 3) AS initial_rate FROM uscis WHERE fiscal_year = 2025
  AND employer_key LIKE 'deloitte%' GROUP BY employer_key ORDER BY ia DESC
Pitfalls:
- One company files under several employer_keys (amazon com services, amazon web services,
  amazon development center u s ...; deloitte consulting, deloitte and touche ...). Use a prefix
  LIKE for the company and say which entities you included.
- The same company's key can change between years, which fakes a drop in a trend: Ernst & Young is
  'ernst young' through FY2024 but mostly 'ernst and young u s' from FY2025; Amazon also appears as
  'amazon web svcs'. For trends, first list the matching keys per fiscal_year
  (WHERE employer_key LIKE '%ernst%young%' GROUP BY fiscal_year, employer_key), then sum the right ones.
- A company may be missing or named differently than in lca/perm. If an employer_key from
  another source returns no rows, try a LIKE on its main words before saying "not found",
  and report unmatched companies as unmatched rather than as zero approvals.
- The file layout changed in FY2023. FY2023 continuing approvals are ~18% lower than FY2022 overall
  (and 30-40% lower at some big employers) while initial approvals are steady: this may be a
  counting change, so warn when comparing continuing/total counts across FY2022 -> FY2023.
- Denial rates were unusually high in FY2018-FY2019 (policy era) and very low from FY2021; say so
  when comparing rates across those years.
- Initial approvals are not lottery odds and not unique hires.""",
)
