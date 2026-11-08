"""USCIS H-1B Employer Data Hub (approvals and denials per employer). Owner: B.

TODO(B): clean the hub files into data/clean/uscis.parquet with build/common.py,
then write the real schema_doc.
"""

from sources.base import SqlSource, data_path

SOURCE = SqlSource(
    name="uscis",
    description=(
        "USCIS H-1B Employer Data Hub by fiscal year: initial and continuing approvals and denials "
        "per employer, with industry (NAICS), state and city. Answers: did an employer's H-1B "
        "petitions actually get approved, and how approval counts changed by year. Cannot answer: "
        "job titles or wages (no occupation data), or calendar-year splits."
    ),
    tables={"uscis": data_path("uscis.parquet")},
    schema_doc="TODO(B): data dictionary for table uscis.",
)
