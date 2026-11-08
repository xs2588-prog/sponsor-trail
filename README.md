# Sponsor Trail

Deep Research agent tracing which employers sponsor H-1B and green cards, by job and year.

**Who it's for:** international students looking for jobs in the US, and the people who advise them.
Ask about any job, place and year range ("Data Scientist in New York, 2020-25", "accountants, last year"),
and the agent checks three government datasets against each other: who filed H-1B applications,
whether USCIS approved them, and whether the same employers went on to sponsor green cards.

Path: **Deep Research** (`"path": "research"` in `submission.json`).

> Status: scaffold. The pipeline runs end to end on a toy example source.
> The three real sources are being cleaned (see "Team" below).

## How it works

```
user question
   └─ Lead (agents/lead.py)          clarify if vague, split into tasks, one per source
        ├─ Researcher-lca   ┐
        ├─ Researcher-uscis ├─ run in parallel, each in a fresh context with only its own SQL tool
        └─ Researcher-perm  ┘
   └─ Lead checks for gaps, sends follow-up tasks (max 2 extra rounds)
   └─ Writer (agents/writer.py)      cited answer + what the data could not answer
```

`/chat` keeps the Project 1 response shape (`response`, `session_id`, `tool_calls`).
Every entry in `tool_calls` has an `agent` field: `lead`, `researcher-<source>` or `writer`.

## Data

| Source | What it answers | Where it comes from | Table |
| --- | --- | --- | --- |
| DOL LCA disclosure data | who files H-1B for which job, where, at what wage | [DOL OFLC performance data](https://www.dol.gov/agencies/eta/foreign-labor/performance), FY2020 to FY2026 Q3 | `lca` |
| USCIS H-1B Employer Data Hub | approvals and denials per employer | USCIS H-1B Employer Data Hub, by fiscal year | `uscis` |
| DOL PERM disclosure data | which employers sponsor green cards | [DOL OFLC performance data](https://www.dol.gov/agencies/eta/foreign-labor/performance), FY2020 to FY2026 Q3 | `perm` |

Offline build: `build/common.py` holds the shared cleaning rules (employer name normalization,
SOC codes, fiscal year). Each source's cleaning script writes `data/clean/<source>.parquet`.
TODO: download and load steps, and where the cleaned files are hosted (GCS).

## Sample queries

TODO: three questions, each with the expected answer and the table it comes from, plus the
answer from the same model with no tools and no system prompt.

| # | Question | Expected answer (source) | Agent answer | No-tools model answer |
| --- | --- | --- | --- | --- |
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |

## Run locally

```bash
uv sync
gcloud auth application-default login   # Vertex AI credentials
uv run app.py                           # http://localhost:8000
uv run pytest
```

Settings are in `.env.example`.

## Deploy

Cloud Run with continuous deployment from this repo's `main` branch.
Set the request timeout to at least 300 seconds (graders wait up to 5 minutes per answer).

## Team

| Member | Researcher + data source | Shared part |
| --- | --- | --- |
| xs2588 | `lca` | Lead, `/chat`, deployment |
| | `uscis` | offline build rules, data hosting, data dictionary |
| | `perm` | Writer, frontend, README |
