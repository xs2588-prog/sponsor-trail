"""TOY example source: copy this file to build a real one.

The data in data/example/ is made up (fake companies). It exists so the whole
pipeline runs before the real sources are cleaned. Turn it off with
SPONSOR_EXAMPLE_SOURCE=0.
"""

from pathlib import Path

from sources.base import SqlSource

EXAMPLE_CSV = Path(__file__).resolve().parent.parent / "data" / "example" / "example_lca.csv"

SOURCE = SqlSource(
    name="example",
    description=(
        "TOY DEMO DATA with made-up companies (Acme Analytics, Blue Harbor Bank, Northwind Health). "
        "Shaped like LCA filings: employer, SOC job code, title, worksite, wage, status, dates. "
        "Use it only when no real source is loaded, and say the numbers are fake."
    ),
    tables={"example_lca": str(EXAMPLE_CSV)},
    schema_doc="""Table example_lca (one row per LCA filing):
- employer_key: normalized employer name (lowercase, no LLC/INC), use it to group companies
- employer_name: name as filed
- soc_code / soc_title: standard job code, e.g. 15-2051 Data Scientists, 13-2011 Accountants and Auditors
- job_title: free text as filed
- worksite_city, worksite_state
- wage_from (number), wage_unit ('Year'), pw_wage_level (I-IV)
- case_status: Certified | Denied | Withdrawn | Certified - Withdrawn
- received_date (YYYY-MM-DD), fiscal_year (Oct-Sep, FY2025 = Oct 2024-Sep 2025), calendar_year
""",
)
