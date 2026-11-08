"""DOL LCA disclosure data (H-1B, H-1B1, E-3 labor condition applications). Owner: A.

TODO(A): clean FY2020-FY2026 files into data/clean/lca.parquet with build/common.py,
then write the real schema_doc (columns, example values, pitfalls).
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
    schema_doc="TODO(A): data dictionary for table lca.",
)
