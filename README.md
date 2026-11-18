# Sponsor Trail

A **Deep Research** agent for international students and career advisers researching US employer sponsorship. It compares employers' H-1B labor condition applications (LCA), USCIS petition decisions, and PERM labor certifications. Its question domain is the employer sponsorship trail across these three distinct stages, by occupation, place and fiscal year—not general visa advice.

**Status:** deployed publicly on Cloud Run at [sponsor-trail-1037056864598.us-east1.run.app](https://sponsor-trail-1037056864598.us-east1.run.app). All three production sources load from the private GCS snapshot, the live Vertex model and SQL tool path were verified end to end, and the three required Agent-vs-no-tools comparisons are recorded below. Register/check this dataset and question domain in the class sign-up sheet before submission; uniqueness cannot be verified from this repository.

## Architecture and Deep Research requirements

- **Lead** (`agents/lead.py`) asks for clarification when the scope is vague, incorporates conversation history into a complete research question, and gives each Researcher a self-contained task.
- **Researchers** (`agents/researcher.py`) run concurrently with `asyncio.gather`, each with a newly created message context and only its source's SQL tool/data dictionary. SQL runs off the event loop. There are at most 6 tasks per round and 6 model turns per Researcher.
- **Lead revisits gaps:** up to 2 extra rounds after the initial fan-out. Cross-source questions can first discover employers in LCA, then query their USCIS/PERM evidence. Unanswerable questions and missing sources are recorded as limitations. The final report discloses reaching the follow-up cap.
- **Writer** (`agents/writer.py`) selects relevant successful query results. Code renders the actual returned columns and values, creates citation IDs, and appends the exact executed SQL. Free-form model claims cannot supply final numbers or citations. When queries contain unique `employer_key` rows, an exact-key comparison combines source metrics while retaining each query's scope. Unmatched employers are never converted to zeros. This deliberately favors auditable tables over unsupported narrative.
- **Show work:** `/chat` returns `response`, `session_id`, `tool_calls`. Every trace entry includes `agent`, `name`, `args`, `result`, including sub-agent SQL calls. The frontend displays events in their recorded order. Researcher failures preserve other completed reports. Request failures/timeouts retain the trace collected so far.

The source prompt explains differences between LCA cases, worker positions, initial/continuing USCIS decisions and PERM certifications. LCA certification does **not** mean an H-1B petition was approved. PERM certification does **not** mean a green card was issued. USCIS has no occupation or worksite field; employer-wide approval rates are not job-specific rates or lottery probabilities.

## Data provenance and loading

Three sources for three team members:

- **DOL LCA disclosure files**, [OFLC performance data](https://www.dol.gov/agencies/eta/foreign-labor/performance). Offline script: `build/clean_lca.py`; runtime table: `lca`. Declared coverage FY2020–FY2026 Q3. Application, occupation, worksite and wage fields.
- **USCIS H-1B Employer Data Hub**, [official hub](https://www.uscis.gov/tools/reports-and-studies/h-1b-employer-data-hub). Offline script: `build/clean_uscis.py`; runtime table: `uscis`. Declared coverage FY2009–FY2026. Initial/continuing approvals and denials, employer filing location and industry; no job titles. Legacy CSV and newer UTF-16 tab-separated exports are supported.
- **DOL PERM disclosure files**, the same [OFLC performance page](https://www.dol.gov/agencies/eta/foreign-labor/performance). Offline script: `build/clean_perm.py`; runtime table: `perm`. Declared coverage FY2020–FY2026 Q3. Employer, occupation, worksite, wages and processing days; worker visa/education fields disappear in the newer form.

Coverage notes in `sources/*.py` describe the intended cleaned snapshot. Confirm actual min/max fiscal years and source files when refreshing data. Do not compare FY2026 partial LCA/PERM totals with full years, or treat a missing field as zero.

The shared offline build (`build/common.py`) normalizes employer names, SOC codes, state names and fiscal years. PERM also includes a limited 2010-to-2018 SOC crosswalk. Name normalization is not a verified corporate-entity mapping: aliases/legal entities can still differ across sources.

### Use the existing GCS snapshot

Project: `sponsor-trail-514122`. Bucket location: `us-east1`.

- `gs://sponsortrail_01/clean_dataset/lca.parquet` — 143.3 MB as displayed by Cloud Console.
- `gs://sponsortrail_01/clean_dataset/uscis.parquet` — 27.4 MB.
- `gs://sponsortrail_01/clean_dataset/perm.parquet` — 34 MB.

The bucket remains private. Cloud Run's service account needs bucket-level **Storage Object Viewer**; public bucket access is unnecessary. Set `SPONSOR_GCS_URI=gs://sponsortrail_01/clean_dataset`. On startup, `sources/remote.py` downloads only these three files into `SPONSOR_DATA_DIR`, checks object generation when reusing files and replaces downloads atomically. The model queries the container-local files with DuckDB. Each source can read only its configured paths; arbitrary files and external network readers are disabled.

To inspect the bucket without downloading its files:

```bash
uv run python -m scripts.check_gcs
```

### Rebuild from raw files

Download the official raw exports to `data/raw/lca/`, `data/raw/uscis/`, `data/raw/perm/`. Government download sites may require a regular browser. USCIS exports should be named `h1b_datahubexport-YYYY.csv`. Do not mix duplicate exports of the same USCIS snapshot, since counts would be duplicated.

```bash
uv run python -m build.clean_lca
uv run python -m build.clean_uscis
uv run python -m build.clean_perm
```

This writes `data/clean/{lca,uscis,perm}.parquet`. With authorized GCP credentials, upload a refreshed snapshot explicitly:

```bash
gcloud storage cp data/clean/lca.parquet data/clean/uscis.parquet data/clean/perm.parquet gs://sponsortrail_01/clean_dataset/
```

Large data is excluded from Git. Restart/redeploy the service to use a refreshed snapshot; running instances retain their existing data until restart.

## Run locally

Use Python 3.12 and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
uv sync --frozen
cp .env.example .env
uv run app.py
```

Open `http://localhost:8000`. With no real data, the tiny made-up `example` source is enabled and clearly labeled. Any available real source automatically hides the example. This toy mode verifies application plumbing only; it cannot be used for final research claims.

For real data/model access, install the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install), then:

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project sponsor-trail-514122
```

In `.env`, set:

```dotenv
VERTEXAI_PROJECT=sponsor-trail-514122
SPONSOR_GCS_URI=gs://sponsortrail_01/clean_dataset
SPONSOR_EXAMPLE_SOURCE=0
SPONSOR_REQUIRED_SOURCES=lca,uscis,perm
```

Use an available Vertex model in `SPONSOR_MODEL`; the deployed and recorded configuration is `vertex_ai/gemini-3.5-flash-lite`. Lead/Researcher/Writer can be configured separately. A browser Console login alone does not create local Application Default Credentials. Never commit `.env` or credential files.

## Three grader sample queries

Reference SQL lives in `scripts/sample_queries.py` and is **not** used as few-shot prompt content. Exact numerical expectations must be generated from the actual snapshot; do not substitute guessed numbers.

1. **FY2025 Data Scientists in NYC:** “In FY2025, which five employer keys had the most certified H-1B LCA cases for Data Scientists where worksite_state is exactly 'NY' and worksite_city is exactly 'New York'? Include case counts. Match SOC 15-2051 OR job titles containing data scientist. Include Certified and Certified - Withdrawn; count cases, not workers; break ties by employer_key. Do not broaden the exact city filter with ILIKE.” Expected: five employer keys with certified case counts, ordered descending; source `lca`, `lca.parquet`.
2. **FY2025 initial approvals:** “Across all US employers in FY2025, which five employer keys had the most USCIS initial H-1B approvals? Show summed initial approvals, initial denials, and initial approval rate rounded to four decimal places. Require at least ten initial decisions; break ties by employer_key. This is an employer-wide question, with no occupation filter.” Expected: five employer keys and summed counts/rates, with the denominator approvals + denials; source `uscis`, `uscis.parquet`.
3. **FY2025 PERM for software developers in NY:** “In FY2025, which five employer keys had the most certified PERM cases for Software Developers (soc_code_2018 = 15-1252) in New York State? Include Certified and Certified - Expired. Show case counts and the exact MEDIAN(processing_days), retaining fractional values such as .5 without casting or rounding; break ties by employer_key. Explain whether this proves that green cards were issued.” Expected: five employer keys, counts and median processing days, with a clear statement that PERM does not prove green-card issuance; source `perm`, `perm.parquet`.

Also try a multi-source question: “For the top five employers filing certified H-1B LCA cases for Data Scientists in NYC in FY2025, check their FY2025 employer-wide initial USCIS approval rates and software/data-science PERM certifications. Report unmatched entities explicitly.” This exercises initial parallel work plus focused follow-ups. Try “I want a job with good visa sponsorship prospects” to exercise clarification.

### Generate the required real model comparisons

With authenticated model/data access:

```bash
uv run python -m scripts.compare_samples --write-readme
```

The script executes the fixed reference SQL, runs the agent, then asks the **same model** the question with one user message, **no tools and no system prompt**. It records the timestamp, model, dataset file hashes, SQL results, complete tool trace and both actual answers in `artifacts/samples/*.json`, then inserts them below. The script checks reference row values against both successful queries from the required source and the final answer tables, and exits with a failure if they differ. Review SQL scope separately: matching values and deterministic rendering do not prove semantic query correctness. The local comparison command forces all agent roles to the same model.

<!-- SAMPLE_RESULTS_START -->
### Recorded model comparisons

Actual calls using `vertex_ai/gemini-3.5-flash-lite`. Baseline: one user message, no tools, no system prompt.

#### lca-ny-ds-2025

In FY2025, which five employer keys had the most certified H-1B LCA cases for Data Scientists where worksite_state is exactly 'NY' and worksite_city is exactly 'New York'? Include case counts. Match SOC 15-2051 OR job titles containing data scientist. Include Certified and Certified - Withdrawn; count cases, not workers; break ties by employer_key. Do not broaden the exact city filter with ILIKE.

**Expected answer (executed reference SQL):**

```json
{
  "ok": true,
  "columns": [
    "employer_key",
    "certified_cases"
  ],
  "rows": [
    [
      "amazon com services",
      164
    ],
    [
      "google",
      112
    ],
    [
      "meta platforms",
      105
    ],
    [
      "jpmorgan chase",
      72
    ],
    [
      "capital one national association",
      55
    ]
  ],
  "truncated": false,
  "sql": "SELECT employer_key, COUNT(*) AS certified_cases\nFROM lca\nWHERE fiscal_year = 2025 AND visa_class = 'H-1B'\n  AND case_status IN ('Certified', 'Certified - Withdrawn')\n  AND worksite_state = 'NY' AND worksite_city = 'New York'\n  AND (soc_code = '15-2051' OR job_title ILIKE '%data scientist%')\nGROUP BY employer_key ORDER BY certified_cases DESC, employer_key LIMIT 5"
}
```

**Agent answer:**

These results come from executed SQL. Counts from different sources measure different things.

### lca [1]

> Find the top 5 employer keys with the most certified H-1B LCA cases (including 'Certified' and 'Certified - Withdrawn') in FY2025 for Data Scientists where worksite_state is exactly 'NY' and worksite_city is exactly 'New York'. Match SOC code 15-2051 OR job titles containing 'data scientist' (case-insensitive search). Count cases (not workers) and break ties alphabetically or consistently by employer_key. Return employer keys and their case counts.

| employer_key | employer_name | case_count |
| --- | --- | --- |
| amazon com services | Amazon.com Services LLC | 164 |
| google | Google LLC | 112 |
| meta platforms | Meta Platforms, Inc | 105 |
| jpmorgan chase | JPMorgan Chase &amp; Co. | 72 |
| capital one national association | Capital One, National Association | 55 |

### Limitations

- The LCA data reflects application filings rather than final USCIS petition approvals or actual hires.
- Discarded a finding whose SQL or value did not match a successful query.
- LCA ≠ H-1B approval; PERM ≠ green card approval. Employer-level USCIS rates are not occupation-specific or lottery odds.

### Sources

[1] lca — executed SQL (years and filters shown below).

```sql
SELECT
    employer_key,
    ANY_VALUE(employer_name) AS employer_name,
    COUNT(*) AS case_count
FROM lca
WHERE fiscal_year = 2025
  AND visa_class = 'H-1B'
  AND case_status IN ('Certified', 'Certified - Withdrawn')
  AND worksite_state = 'NY'
  AND worksite_city = 'New York'
  AND (soc_code = '15-2051' OR job_title ILIKE '%data scientist%')
GROUP BY employer_key
ORDER BY case_count DESC, employer_key ASC
LIMIT 5
```


Reference values found in source query results: **True**; in final tables: **True**. Review SQL scope separately.

**Same-model answer without tools or system prompt:**

````
```json
[
  {
    "employer_key": "GOOGLE LLC",
    "case_count": 526
  },
  {
    "employer_key": "MORGAN STANLEY & CO. LLC",
    "case_count": 270
  },
  {
    "employer_key": "JPMORGAN CHASE BANK, N.A.",
    "case_count": 218
  },
  {
    "employer_key": "BLOOMBERG, L.P.",
    "case_count": 182
  },
  {
    "employer_key": "GOLDMAN SACHS & CO. LLC",
    "case_count": 161
  }
]
```
````

Full tool trace: [artifacts/samples/lca-ny-ds-2025.json](artifacts/samples/lca-ny-ds-2025.json)

#### uscis-initial-2025

Across all US employers in FY2025, which five employer keys had the most USCIS initial H-1B approvals? Show summed initial approvals, initial denials, and initial approval rate rounded to four decimal places. Require at least ten initial decisions; break ties by employer_key. This is an employer-wide question, with no occupation filter.

**Expected answer (executed reference SQL):**

```json
{
  "ok": true,
  "columns": [
    "employer_key",
    "initial_approvals",
    "initial_denials",
    "initial_rate"
  ],
  "rows": [
    [
      "amazon com services",
      3003,
      45,
      0.9852
    ],
    [
      "meta platforms",
      1554,
      14,
      0.9911
    ],
    [
      "microsoft",
      1394,
      6,
      0.9957
    ],
    [
      "google",
      1042,
      6,
      0.9943
    ],
    [
      "amazon development center u s",
      895,
      6,
      0.9933
    ]
  ],
  "truncated": false,
  "sql": "SELECT employer_key, SUM(initial_approvals) AS initial_approvals,\nSUM(initial_denials) AS initial_denials,\nROUND(SUM(initial_approvals)::DOUBLE / NULLIF(SUM(initial_approvals) + SUM(initial_denials), 0), 4) AS initial_rate\nFROM uscis WHERE fiscal_year = 2025\nGROUP BY employer_key HAVING SUM(initial_approvals) + SUM(initial_denials) >= 10\nORDER BY initial_approvals DESC, employer_key LIMIT 5"
}
```

**Agent answer:**

These results come from executed SQL. Counts from different sources measure different things.

### uscis [1]

> Find the top five employers by USCIS initial H-1B approvals in FY2025. Return the employer_key, sum of initial approvals, sum of initial denials, and the initial approval rate rounded to four decimal places. Filter for employers with at least 10 initial decisions (approvals + denials) in FY2025. Break ties alphabetically by employer_key.

| employer_key | employer_name | total_initial_approvals | total_initial_denials | initial_approval_rate |
| --- | --- | --- | --- | --- |
| amazon com services | AMAZON COM SERVICES LLC | 3003 | 45 | 0.9852 |
| meta platforms | META PLATFORMS INC | 1554 | 14 | 0.9911 |
| microsoft | MICROSOFT CORPORATION | 1394 | 6 | 0.9957 |
| google | GOOGLE LLC | 1042 | 6 | 0.9943 |
| amazon development center u s | AMAZON DEVELOPMENT CENTER U S INC | 895 | 6 | 0.9933 |

### Limitations

- The USCIS dataset provides petition counts and approval/denial metrics by employer filing location and NAICS sector, but does not contain information on job titles, occupations, salaries, or specific worksite locations.
- Discarded a finding whose SQL or value did not match a successful query.
- LCA ≠ H-1B approval; PERM ≠ green card approval. Employer-level USCIS rates are not occupation-specific or lottery odds.

### Sources

[1] uscis — executed SQL (years and filters shown below).

```sql
SELECT
    employer_key,
    ANY_VALUE(employer_name) AS employer_name,
    SUM(initial_approvals) AS total_initial_approvals,
    SUM(initial_denials) AS total_initial_denials,
    ROUND(SUM(initial_approvals)::NUMERIC / NULLIF(SUM(initial_approvals) + SUM(initial_denials), 0), 4) AS initial_approval_rate
FROM uscis
WHERE fiscal_year = 2025
GROUP BY employer_key
HAVING (SUM(initial_approvals) + SUM(initial_denials)) >= 10
ORDER BY total_initial_approvals DESC, employer_key ASC
LIMIT 5
```


Reference values found in source query results: **True**; in final tables: **True**. Review SQL scope separately.

**Same-model answer without tools or system prompt:**

````
```json
[
  {
    "employer_key": "AMAZON.COM SERVICES LLC",
    "initial_approvals": 7378,
    "initial_denials": 194,
    "initial_approval_rate": 0.9744
  },
  {
    "employer_key": "COGNIZANT TECHNOLOGY SOLUTIONS US CORP",
    "initial_approvals": 4279,
    "initial_denials": 69,
    "initial_approval_rate": 0.9841
  },
  {
    "employer_key": "TATA CONSULTANCY SERVICES LIMITED",
    "initial_approvals": 3139,
    "initial_denials": 71,
    "initial_approval_rate": 0.9789
  },
  {
    "employer_key": "GOOGLE LLC",
    "initial_approvals": 2983,
    "initial_denials": 49,
    "initial_approval_rate": 0.9838
  },
  {
    "employer_key": "MICROSOFT CORPORATION",
    "initial_approvals": 2728,
    "initial_denials": 46,
    "initial_approval_rate": 0.9834
  }
]
```
````

Full tool trace: [artifacts/samples/uscis-initial-2025.json](artifacts/samples/uscis-initial-2025.json)

#### perm-ny-software-2025

In FY2025, which five employer keys had the most certified PERM cases for Software Developers (soc_code_2018 = 15-1252) in New York State? Include Certified and Certified - Expired. Show case counts and the exact MEDIAN(processing_days), retaining fractional values such as .5 without casting or rounding; break ties by employer_key. Explain whether this proves that green cards were issued.

**Expected answer (executed reference SQL):**

```json
{
  "ok": true,
  "columns": [
    "employer_key",
    "certified_cases",
    "median_processing_days"
  ],
  "rows": [
    [
      "bloomberg l p",
      172,
      469.0
    ],
    [
      "ibm",
      84,
      484.0
    ],
    [
      "goldman sachs services",
      60,
      491.0
    ],
    [
      "morgan stanley services group",
      46,
      489.5
    ],
    [
      "mitchell martin",
      29,
      499.0
    ]
  ],
  "truncated": false,
  "sql": "SELECT employer_key, COUNT(*) AS certified_cases,\nMEDIAN(processing_days) AS median_processing_days\nFROM perm WHERE fiscal_year = 2025 AND worksite_state = 'NY'\nAND soc_code_2018 = '15-1252' AND case_status IN ('Certified', 'Certified - Expired')\nGROUP BY employer_key ORDER BY certified_cases DESC, employer_key LIMIT 5"
}
```

**Agent answer:**

These results come from executed SQL. Counts from different sources measure different things.

### perm [1]

> Find the top 5 employer keys with the most certified PERM cases (including 'Certified' and 'Certified - Expired') for Software Developers (soc_code_2018: 15-1252) in New York State (NY) for FY2025. For each of the 5 employers, return the employer_key, the exact case count, and the exact MEDIAN(processing_days) retaining fractional values such as .5 without rounding or casting. Break any ties alphabetically by employer_key.

| employer_key | cnt | med_days |
| --- | --- | --- |
| bloomberg l p | 172 | 469.0 |
| ibm | 84 | 484.0 |
| goldman sachs services | 60 | 491.0 |
| morgan stanley services group | 46 | 489.5 |
| mitchell martin | 29 | 499.0 |

### Limitations

- The PERM dataset does not include subsequent green card adjudication outcomes (I-140/I-485) or worker visa classes for FY2025 due to form disclosure changes.
- LCA ≠ H-1B approval; PERM ≠ green card approval. Employer-level USCIS rates are not occupation-specific or lottery odds.

### Sources

[1] perm — executed SQL (years and filters shown below).

```sql
SELECT employer_key, COUNT(*) AS cnt, MEDIAN(processing_days) AS med_days FROM perm WHERE fiscal_year = 2025 AND soc_code_2018 = '15-1252' AND worksite_state = 'NY' AND case_status IN ('Certified', 'Certified - Expired') GROUP BY employer_key ORDER BY cnt DESC, employer_key ASC LIMIT 5
```


Reference values found in source query results: **True**; in final tables: **True**. Review SQL scope separately.

**Same-model answer without tools or system prompt:**

```
Based on the PERM disclosure data for FY2025, here are the top five employers with the most certified PERM cases (including both *Certified* and *Certified - Expired*) for Software Developers (SOC Code 15-1252) in New York State.

### Top 5 Employers for Software Developers (NY, FY2025)

| Rank | Employer Key | Case Count | Median Processing Days |
| :--- | :--- | :--- | :--- |
| 1 | *[Employer Key 1]* | *[Count]* | *[Exact Median, e.g., 185.5]* |
| 2 | *[Employer Key 2]* | *[Count]* | *[Exact Median]* |
| 3 | *[Employer Key 3]* | *[Count]* | *[Exact Median]* |
| 4 | *[Employer Key 4]* | *[Count]* | *[Exact Median]* |
| 5 | *[Employer Key 5]* | *[Count]* | *[Exact Median]* |

*(Note: In a live data environment, exact database queries against the Department of Labor Disclosure Data would populate these specific employer keys, counts, and unrounded fractional medians broken alphabetically by key in the event of ties.)*

---

### Does this prove that green cards were issued?

**No, this does not prove that green cards were issued.**

A certified PERM (Program Electronic Review Management) application—form ETA-9089 approved by the U.S. Department of Labor (DOL)—is merely the **first mandatory step** in a multi-stage employment-based green card (Permanent Residency) process.

Certification signifies only that the DOL has determined:
1. There are insufficient able, willing, qualified, and available U.S. workers for the job position in the area of intended employment.
2. The employment of the foreign national will not adversely affect the wages and working conditions of similarly employed U.S. workers.

To actually receive a green card, the beneficiary and employer must successfully complete subsequent phases which are **not** tracked or guaranteed by a PERM certification:

1. **Form I-140 (Immigrant Petition for Alien Worker):** Filed with U.S. Citizenship and Immigration Services (USCIS) to prove the employer's financial ability to pay the offered wage and the worker's qualifications for the position.
2. **Visa Availability (Priority Dates):** Depending on the applicant's country of birth and preference category (typically EB-2 or EB-3 for software developers), a visa number must be currently available under the State Department’s Visa Bulletin, which often involves significant backlogs.
3. **Form I-485 (Adjustment of Status) or Consular Processing:** The final application to adjust status to lawful permanent resident (or obtain an immigrant visa abroad), which includes comprehensive background, security, and medical checks.

A PERM certification expires after 180 days if not filed with USCIS as part of an I-140 petition, and even if an I-140 is approved, a green card is never officially issued until the final adjustment of status or consular visa is granted. Therefore, PERM data represents approved labor market tests, not final green card issuance.
```

Full tool trace: [artifacts/samples/perm-ny-software-2025.json](artifacts/samples/perm-ny-software-2025.json)

<!-- SAMPLE_RESULTS_END -->

## Tests

```bash
uv run --frozen pytest -q
```

Tests use a deterministic fake model and do not require Vertex/GCS credentials. They cover cleaning, SQL errors/read isolation, real-vs-demo source selection, parallel fresh contexts, clarification continuity, follow-up caps, failure isolation, rejected unexecuted evidence, deterministic Writer citations, and atomic/versioned GCS downloads. They are not a live model accuracy evaluation. GitHub Actions runs these checks on pushes and pull requests.

## Submission

`submission.json` lists the team identifiers (`yc4752`, `st3813`, `xs2588`), the `research` path and the final public Cloud Run URL. Confirm the identifiers before submission.

The three actual model comparisons above were recorded and checked against independently executed reference SQL. Check the class sign-up sheet for dataset/question uniqueness and submit the repository URL on Courseworks. If the repository is private, grant the grader accounts specified in the assignment access to it.

### Known limits

Conversation history is kept in memory (up to 12 messages per session, 512 sessions per process). Cloud Run restarts or routing to another instance can lose clarification history; session affinity is best effort. Use one instance for a predictable classroom demo or persist sessions externally for stronger guarantees. Exact employer-key matching can miss aliases; this is disclosed instead of guessing a match. Model-generated SQL still needs validation against the question, especially occupation-code changes, partial years, and entity-level interpretation.
