"""Fixed grader questions and independently executable reference SQL (not prompt examples)."""
SAMPLES = [
    {
        'id': 'lca-ny-ds-2025', 'source': 'lca',
        'question': "In FY2025, which five employer keys had the most certified H-1B LCA cases for Data Scientists where worksite_state is exactly 'NY' and worksite_city is exactly 'New York'? Include case counts. Match SOC 15-2051 OR job titles containing data scientist. Include Certified and Certified - Withdrawn; count cases, not workers; break ties by employer_key. Do not broaden the exact city filter with ILIKE.",
        'expectation': 'Five employer keys and their case counts from lca, ordered by count descending then key. These are LCA certifications, not USCIS approvals or hires.',
        'sql': """SELECT employer_key, COUNT(*) AS certified_cases
FROM lca
WHERE fiscal_year = 2025 AND visa_class = 'H-1B'
  AND case_status IN ('Certified', 'Certified - Withdrawn')
  AND worksite_state = 'NY' AND worksite_city = 'New York'
  AND (soc_code = '15-2051' OR job_title ILIKE '%data scientist%')
GROUP BY employer_key ORDER BY certified_cases DESC, employer_key LIMIT 5""",
    },
    {
        'id': 'uscis-initial-2025', 'source': 'uscis',
        'question': 'Across all US employers in FY2025, which five employer keys had the most USCIS initial H-1B approvals? Show summed initial approvals, initial denials, and initial approval rate rounded to four decimal places. Require at least ten initial decisions; break ties by employer_key. This is an employer-wide question, with no occupation filter.',
        'expectation': 'Five employer keys ranked by summed initial approvals, initial denials and initial approval rate (0 to 1) from uscis. Not a job-specific rate or lottery probability.',
        'sql': """SELECT employer_key, SUM(initial_approvals) AS initial_approvals,
SUM(initial_denials) AS initial_denials,
ROUND(SUM(initial_approvals)::DOUBLE / NULLIF(SUM(initial_approvals) + SUM(initial_denials), 0), 4) AS initial_rate
FROM uscis WHERE fiscal_year = 2025
GROUP BY employer_key HAVING SUM(initial_approvals) + SUM(initial_denials) >= 10
ORDER BY initial_approvals DESC, employer_key LIMIT 5""",
    },
    {
        'id': 'perm-ny-software-2025', 'source': 'perm',
        'question': 'In FY2025, which five employer keys had the most certified PERM cases for Software Developers (soc_code_2018 = 15-1252) in New York State? Include Certified and Certified - Expired. Show case counts and the exact MEDIAN(processing_days), retaining fractional values such as .5 without casting or rounding; break ties by employer_key. Explain whether this proves that green cards were issued.',
        'expectation': 'Five employer keys, PERM certification counts and median processing days from perm. Explicitly state that PERM certification does not prove a green card was issued.',
        'sql': """SELECT employer_key, COUNT(*) AS certified_cases,
MEDIAN(processing_days) AS median_processing_days
FROM perm WHERE fiscal_year = 2025 AND worksite_state = 'NY'
AND soc_code_2018 = '15-1252' AND case_status IN ('Certified', 'Certified - Expired')
GROUP BY employer_key ORDER BY certified_cases DESC, employer_key LIMIT 5""",
    },
]
