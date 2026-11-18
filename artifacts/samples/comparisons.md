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
