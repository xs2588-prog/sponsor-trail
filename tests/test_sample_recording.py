"""The README generator must record actual calls/reference queries, never invented answers."""
import asyncio
import json
from argparse import Namespace

import pandas as pd

from agents import lead, llm
from scripts import compare_samples
from scripts.sample_queries import SAMPLES
from sources.base import SqlSource
import sources
import sources.remote


def make_sources(tmp_path):
    rows = {
        'lca': [
            {'employer_key': 'alpha', 'fiscal_year': 2025, 'visa_class': 'H-1B', 'case_status': 'Certified', 'worksite_state': 'NY', 'worksite_city': 'New York', 'soc_code': '15-2051', 'job_title': 'DS'},
            {'employer_key': 'alpha', 'fiscal_year': 2025, 'visa_class': 'H-1B', 'case_status': 'Certified - Withdrawn', 'worksite_state': 'NY', 'worksite_city': 'New York', 'soc_code': '15-2041', 'job_title': 'Data Scientist'},
            {'employer_key': 'beta', 'fiscal_year': 2025, 'visa_class': 'E-3 Australian', 'case_status': 'Certified', 'worksite_state': 'NY', 'worksite_city': 'New York', 'soc_code': '15-2051', 'job_title': 'DS'},
        ],
        'uscis': [
            {'employer_key': 'alpha', 'fiscal_year': 2025, 'initial_approvals': 8, 'initial_denials': 2},
            {'employer_key': 'alpha', 'fiscal_year': 2025, 'initial_approvals': 10, 'initial_denials': 0},
            {'employer_key': 'beta', 'fiscal_year': 2025, 'initial_approvals': 1, 'initial_denials': 0},
        ],
        'perm': [
            {'employer_key': 'alpha', 'fiscal_year': 2025, 'worksite_state': 'NY', 'soc_code_2018': '15-1252', 'case_status': 'Certified', 'processing_days': 100},
            {'employer_key': 'alpha', 'fiscal_year': 2025, 'worksite_state': 'NY', 'soc_code_2018': '15-1252', 'case_status': 'Certified - Expired', 'processing_days': 200},
            {'employer_key': 'beta', 'fiscal_year': 2025, 'worksite_state': 'NY', 'soc_code_2018': '15-1252', 'case_status': 'Denied', 'processing_days': 10},
        ],
    }
    result = {}
    for name, records in rows.items():
        path = tmp_path / f'{name}.csv'
        pd.DataFrame(records).to_csv(path, index=False)
        result[name] = SqlSource(name, name, {name: str(path)}, '')
    return result


def test_reference_queries_apply_the_documented_filters(tmp_path):
    sources = make_sources(tmp_path)
    results = [sources[sample['source']].run_sql(sample['sql']) for sample in SAMPLES]
    assert all(result['ok'] for result in results)
    assert results[0]['rows'] == [['alpha', 2]]
    assert results[1]['rows'] == [['alpha', 18, 2, 0.9]]
    assert results[2]['rows'] == [['alpha', 2, 150.0]]


def test_generator_records_no_system_no_tools_baseline_and_real_traces(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sources, 'active_sources', lambda: make_sources(tmp_path))
    monkeypatch.setattr(sources.remote, 'sync_from_gcs', lambda: [])
    for role in ('LEAD', 'RESEARCHER', 'WRITER'):
        monkeypatch.setenv(f'SPONSOR_{role}_MODEL', 'test-model')
    baseline_calls = []
    async def baseline(messages, tools=None, role=None):
        assert len(messages) == 1 and messages[0]['role'] == 'user' and tools is None
        baseline_calls.append(messages)
        return {'content': 'Actual mocked baseline response'}
    async def agent(question, history):
        sample = next(sample for sample in SAMPLES if sample['question'] == question)
        result = make_sources(tmp_path)[sample['source']].run_sql(sample['sql'])
        table = '\n'.join('| ' + ' | '.join(str(cell) for cell in row) + ' |' for row in result['rows'])
        return 'Actual mocked agent response [1]\n' + table, [{'agent': 'researcher-' + sample['source'], 'name': 'run_sql',
                                                    'result': json.dumps(result), 'args': {'sql': sample['sql']}}]
    monkeypatch.setattr(llm, 'complete', baseline)
    monkeypatch.setattr(lead, 'run', agent)
    (tmp_path / 'README.md').write_text('Before\n<!-- SAMPLE_RESULTS_START -->\nPending\n<!-- SAMPLE_RESULTS_END -->\nAfter')
    asyncio.run(compare_samples.run(Namespace(model='test-model', url=None, write_readme=True)))
    assert len(baseline_calls) == 3
    saved = json.loads((tmp_path / 'artifacts/samples/lca-ny-ds-2025.json').read_text())
    assert saved['reference']['rows'] == [['alpha', 2]]
    assert saved['baseline'] == 'Actual mocked baseline response'
    assert saved['agent']['tool_calls'][0]['name'] == 'run_sql'
    readme = (tmp_path / 'README.md').read_text()
    assert 'Before' in readme and 'After' in readme and 'Pending' not in readme
    assert 'Actual mocked agent response' in readme and 'Actual mocked baseline response' in readme


def test_reference_match_rejects_irrelevant_queries_and_accepts_extra_columns():
    reference = {'rows': [['alpha', 18, 2, 0.9]]}
    assert not compare_samples.reference_matches(reference, [{'rows': [[1]]}])
    assert not compare_samples.reference_matches(reference, [{'rows': [['alpha', 18, 2, 0.5]]}])
    assert compare_samples.reference_matches(reference, [{'rows': [['alpha', 'Alpha LLC', 18, 2, 0.900000001]]}])


def test_predeploy_check_catches_missing_evidence_without_requiring_url(tmp_path):
    from scripts.validate_submission import validate_local
    for name in ('app.py', 'pyproject.toml', 'uv.lock'):
        (tmp_path / name).write_text('placeholder')
    (tmp_path / 'README.md').write_text('Not yet recorded.')
    (tmp_path / 'submission.json').write_text(json.dumps({
        'authors': ['a', 'b', 'c'], 'path': 'research', 'deploy_url': 'https://REPLACE-ME.run.app'}))
    errors = validate_local(tmp_path, predeploy=True)
    assert any('README' in error for error in errors)
    assert sum('Missing recorded comparison' in error for error in errors) == 3
    assert not any('deploy_url' in error for error in errors)
    assert any('deploy_url' in error for error in validate_local(tmp_path))


def test_correct_hidden_query_does_not_make_a_wrong_answer_pass():
    reference = {'rows': [['alpha', 18, 2, 0.9]]}
    assert not compare_samples.answer_matches(reference, 'The answer is unavailable.')
    assert not compare_samples.answer_matches(reference, '| alpha | 18 | 2 | 0.5 |')
    assert compare_samples.answer_matches(reference, '| alpha | 18 | 2 | 0.9 |')
