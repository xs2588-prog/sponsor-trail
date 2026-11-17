# Sponsor Trail

A **Deep Research** agent for international students and career advisers researching US employer sponsorship. It compares employers' H-1B labor condition applications (LCA), USCIS petition decisions, and PERM labor certifications. Its question domain is the employer sponsorship trail across these three distinct stages, by occupation, place and fiscal year—not general visa advice.

**Status:** the code, offline cleaners and regression tests are implemented. Three production parquet files were verified in the private GCS bucket using the Cloud Console. Live model accuracy, the recorded sample comparisons and the deployed URL still require an authenticated run; they are not claimed complete. Register/check this dataset and question domain in the class sign-up sheet before submission; uniqueness cannot be verified from this repository.

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

Use an available Vertex model in `SPONSOR_MODEL`; the inherited configuration is `vertex_ai/gemini-3.5-flash-lite` and still needs a live availability/quota check in this project. Lead/Researcher/Writer can be configured separately. A browser Console login alone does not create local Application Default Credentials. Never commit `.env` or credential files.

## Three grader sample queries

Reference SQL lives in `scripts/sample_queries.py` and is **not** used as few-shot prompt content. Exact numerical expectations must be generated from the actual snapshot; do not substitute guessed numbers.

1. **FY2025 Data Scientists in NYC:** “In FY2025, which five employer keys had the most certified H-1B LCA cases for Data Scientists at New York City, NY worksites? Include case counts. Match SOC 15-2051 OR job titles containing data scientist. Include Certified and Certified - Withdrawn; count cases, not workers; break ties by employer_key.” Expected: five employer keys with certified case counts, ordered descending; source `lca`, `lca.parquet`.
2. **FY2025 initial approvals:** “Across all US employers in FY2025, which five employer keys had the most USCIS initial H-1B approvals? Show summed initial approvals, initial denials, and initial approval rate rounded to four decimal places. Require at least ten initial decisions; break ties by employer_key. This is an employer-wide question, with no occupation filter.” Expected: five employer keys and summed counts/rates, with the denominator approvals + denials; source `uscis`, `uscis.parquet`.
3. **FY2025 PERM for software developers in NY:** “In FY2025, which five employer keys had the most certified PERM cases for Software Developers (soc_code_2018 = 15-1252) in New York State? Include Certified and Certified - Expired. Show case counts and median processing_days; break ties by employer_key. Explain whether this proves that green cards were issued.” Expected: five employer keys, counts and median processing days, with a clear statement that PERM does not prove green-card issuance; source `perm`, `perm.parquet`.

Also try a multi-source question: “For the top five employers filing certified H-1B LCA cases for Data Scientists in NYC in FY2025, check their FY2025 employer-wide initial USCIS approval rates and software/data-science PERM certifications. Report unmatched entities explicitly.” This exercises initial parallel work plus focused follow-ups. Try “I want a job with good visa sponsorship prospects” to exercise clarification.

### Generate the required real model comparisons

With authenticated model/data access:

```bash
uv run python -m scripts.compare_samples --write-readme
```

The script executes the fixed reference SQL, runs the agent, then asks the **same model** the question with one user message, **no tools and no system prompt**. It records the timestamp, model, dataset file hashes, SQL results, complete tool trace and both actual answers in `artifacts/samples/*.json`, then inserts them below. The script checks reference row values against both successful queries from the required source and the final answer tables, and exits with a failure if they differ. Review SQL scope separately: matching values and deterministic rendering do not prove semantic query correctness. The local comparison command forces all agent roles to the same model.

<!-- SAMPLE_RESULTS_START -->
**Not yet recorded.** Real model comparisons require GCP authentication. No model answers or exact expected company counts have been fabricated. Run the command above and review the inserted results before submission.
<!-- SAMPLE_RESULTS_END -->

## Tests

```bash
uv run --frozen pytest -q
```

Tests use a deterministic fake model and do not require Vertex/GCS credentials. They cover cleaning, SQL errors/read isolation, real-vs-demo source selection, parallel fresh contexts, clarification continuity, follow-up caps, failure isolation, rejected unexecuted evidence, deterministic Writer citations, and atomic/versioned GCS downloads. They are not a live model accuracy evaluation. GitHub Actions runs these checks on pushes and pull requests.

## Submission

`submission.json` lists the team identifiers (`yc4752`, `st3813`, `xs2588`) and the `research` path. Confirm the identifiers and replace the placeholder `deploy_url` with the final service URL before submission. Follow the course-provided deployment guide separately; this repository does not maintain a deployment guide or custom deployment pipeline.

Record and review the three actual model comparisons above, check the class sign-up sheet for dataset/question uniqueness, and submit the repository URL on Courseworks. If the repository is private, grant the grader accounts specified in the assignment access to it.

### Known limits

Conversation history is kept in memory (up to 12 messages per session, 512 sessions per process). Cloud Run restarts or routing to another instance can lose clarification history; session affinity is best effort. Use one instance for a predictable classroom demo or persist sessions externally for stronger guarantees. Exact employer-key matching can miss aliases; this is disclosed instead of guessing a match. Model-generated SQL still needs validation against the question, especially occupation-code changes, partial years, and entity-level interpretation.
