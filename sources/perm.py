"""DOL PERM disclosure data (green card labor certifications). Owner: C.

TODO(C): clean FY2020-FY2026 files into data/clean/perm.parquet with build/common.py,
then write the real schema_doc.
"""

from sources.base import SqlSource, data_path

SOURCE = SqlSource(
    name="perm",
    description=(
        "DOL PERM disclosure data, FY2020 to FY2026 Q3: green card labor certification cases with "
        "employer, SOC job code, job title, worksite, offered wage, case status and dates. Answers: "
        "which employers sponsor green cards for which jobs, and how often they are certified. "
        "Cannot answer: later I-140/I-485 outcomes or priority-date waits."
    ),
    tables={"perm": data_path("perm.parquet")},
    schema_doc="TODO(C): data dictionary for table perm.",
)
