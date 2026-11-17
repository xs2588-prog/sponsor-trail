"""Regression tests for the Deep Research rubric, with deterministic model responses."""
import asyncio
import json

from fastapi.testclient import TestClient

from agents import lead, llm, researcher, writer
from server.main import app
from sources.base import SqlSource
from sources.example import SOURCE


def test_unexecuted_or_mismatched_claim_cannot_become_evidence(monkeypatch):
    async def fake(*args, **kwargs):
        return {'content': json.dumps({'findings': [{'claim': '999 filings', 'value': 999,
                'citation': {'sql': 'SELECT COUNT(*) FROM example_lca'}}], 'gaps': []})}
    monkeypatch.setattr(llm, 'complete', fake)
    report, calls = asyncio.run(researcher.run(SOURCE, 'count'))
    assert report['findings'] == report['evidence'] == calls == []
    answer = asyncio.run(writer.run('count filings', [report]))
    assert '999' not in answer and 'no data-backed claim' in answer


def test_failed_queries_are_not_evidence():
    report = researcher.ground_report({'findings': []}, 'example', 'count', [
        {'name': 'run_sql', 'result': json.dumps({'ok': False, 'error': 'bad SQL'})}])
    assert report['evidence'] == []


def test_writer_cannot_invent_ids_or_change_values(monkeypatch):
    evidence = {'source': 'lca', 'task': 'count', 'sql': 'SELECT 7 AS n',
                'columns': ['n'], 'rows': [[7]], 'truncated': False}
    async def fake(*args, **kwargs):
        return {'content': '{"evidence_ids": [999], "text": "999 companies"}'}
    monkeypatch.setattr(llm, 'complete', fake)
    answer = asyncio.run(writer.run('count', [{'evidence': [evidence], 'gaps': []}]))
    assert '[999]' not in answer and '999 companies' not in answer
    assert '| 7 |' in answer and '[1] lca' in answer and 'SELECT 7 AS n' in answer


def test_parallel_researchers_have_fresh_contexts(monkeypatch):
    async def scenario():
        arrived = 0
        both = asyncio.Event()
        contexts = []
        async def fake(messages, tools=None, role='researcher'):
            nonlocal arrived
            contexts.append(messages)
            assert len(messages) == 2  # no other Researcher's history
            arrived += 1
            if arrived == 2:
                both.set()
            await asyncio.wait_for(both.wait(), timeout=1)
            return {'content': '{"findings": [], "gaps": []}'}
        monkeypatch.setattr(llm, 'complete', fake)
        reports = await lead._fan_out([{'source': 'example', 'task': 'one'},
                                      {'source': 'example', 'task': 'two'}], {'example': SOURCE}, [])
        assert len(reports) == 2 and contexts[0] is not contexts[1]
        assert not any('model call failed' in gap for report in reports for gap in report['gaps'])
        assert contexts[0][1]['content'] != contexts[1][1]['content']
    asyncio.run(scenario())


def test_gap_followups_are_capped_and_preserve_clarification(monkeypatch):
    checks = []
    written = []
    tasks = []
    async def fake(messages, tools=None, role='researcher'):
        if '"action"' in messages[0]['content']:
            assert 'New York' in str(messages)
            return {'content': json.dumps({'action': 'research', 'resolved_question': '2025',
                    'tasks': [{'source': 'example', 'task': 'count'}]})}
        checks.append(messages[1]['content'])
        return {'content': '{"done": false, "tasks": [{"source": "example", "task": "more"}]}'}
    async def research(source, task):
        tasks.append(task)
        return {'source': source.name, 'evidence': [], 'gaps': []}, []
    async def write(question, reports):
        written.append(question)
        return 'ok'
    monkeypatch.setattr(llm, 'complete', fake)
    monkeypatch.setattr(researcher, 'run', research)
    monkeypatch.setattr(writer, 'run', write)
    monkeypatch.setattr(lead, 'active_sources', lambda: {'example': SOURCE})
    asyncio.run(lead.run('2025', [{'role': 'user', 'content': 'Data scientists in New York'},
                                 {'role': 'assistant', 'content': 'Which year?'}]))
    assert len(checks) == lead.MAX_GAP_ROUNDS and len(tasks) == 1 + lead.MAX_GAP_ROUNDS
    assert all('New York' in text and '2025' in text for text in checks + written)


def test_one_researcher_failure_keeps_other_results(monkeypatch):
    async def research(source, task):
        if task == 'bad':
            raise RuntimeError('provider failed')
        return {'source': 'example', 'findings': [], 'evidence': [], 'gaps': ['good result']}, []
    monkeypatch.setattr(researcher, 'run', research)
    calls = []
    reports = asyncio.run(lead._fan_out([{'source': 'example', 'task': 'bad'},
                                        {'source': 'example', 'task': 'good'}], {'example': SOURCE}, calls))
    assert 'failed' in reports[0]['gaps'][0] and reports[1]['gaps'] == ['good result']
    assert calls[-1]['agent'] == 'researcher-example'


def test_real_source_hides_demo(monkeypatch, tmp_path):
    from sources import active_sources
    import sources
    path = tmp_path / 'real.csv'
    path.write_text('n\n1\n')
    real = SqlSource('lca', 'real', {'lca': str(path)}, 'n')
    monkeypatch.setattr(sources, 'ALL_SOURCES', [SOURCE, real])
    assert list(active_sources()) == ['lca']


def test_sql_cannot_read_another_file(tmp_path):
    secret = tmp_path / 'private.csv'
    secret.write_text('secret\nprivate-value\n')
    result = SOURCE.run_sql(f"SELECT * FROM read_csv_auto('{secret}')")
    assert result['ok'] is False
    assert SOURCE.run_sql('SELECT COUNT(*) FROM example_lca')['rows'] == [[7]]


def test_empty_messages_rejected_and_sources_disclosed():
    client = TestClient(app)
    assert client.post('/chat', json={'message': '   '}).status_code == 422
    status = client.get('/api/status').json()
    assert status['demo'] and status['missing_sources'] == ['lca', 'uscis', 'perm']


def test_required_sources_fail_startup(monkeypatch):
    monkeypatch.setenv('SPONSOR_REQUIRED_SOURCES', 'lca,uscis,perm')
    monkeypatch.delenv('SPONSOR_GCS_URI', raising=False)
    import pytest
    with pytest.raises(RuntimeError, match='Required data sources missing'):
        with TestClient(app):
            pass


def test_comparison_uses_exact_keys_and_preserves_missing_values():
    evidence = [
        {'source': 'lca', 'task': 'LCA FY2025', 'sql': 'SELECT ... FROM lca',
         'columns': ['employer_key', 'cases'], 'rows': [['acme', 7], ['other', 2]]},
        {'source': 'uscis', 'task': 'USCIS FY2025', 'sql': 'SELECT ... FROM uscis',
         'columns': ['employer_key', 'approvals'], 'rows': [['acme', 5], ['acme west', 3]]},
    ]
    answer = writer.render('compare employers', evidence, [1, 2], [])
    assert 'Cross-source employer comparison' in answer
    assert '| acme | 7 | 5 |' in answer
    assert '| other | 2 | unmatched |' in answer
    assert '| acme west | unmatched | 3 |' in answer
    assert 'lca.cases [1]' in answer and 'uscis.approvals [2]' in answer


def test_nonunique_keys_do_not_create_false_cross_source_join():
    evidence = [
        {'source': 'lca', 'columns': ['employer_key', 'year'], 'rows': [['a', 2024], ['a', 2025]]},
        {'source': 'uscis', 'columns': ['employer_key', 'year'], 'rows': [['a', 2025]]},
    ]
    assert writer.compare_employers(evidence, [1, 2]) == []


def test_sql_parser_allows_keywords_inside_literals_but_rejects_mutation():
    assert SOURCE.run_sql("SELECT 'update; set' AS text")['rows'] == [['update; set']]
    assert not SOURCE.run_sql('WITH c AS (SELECT 1) DELETE FROM example_lca')['ok']
    assert not SOURCE.run_sql('SELECT 1; SELECT 2')['ok']
    assert not SOURCE.run_sql(['SELECT 1'])['ok']


def test_timeout_keeps_trace_already_collected(monkeypatch):
    import server.main as server
    async def slow(question, history, trace=None):
        trace.append({'agent': 'lead', 'name': 'plan', 'args': {}, 'result': '{}'})
        await asyncio.Event().wait()
    monkeypatch.setattr(lead, 'run', slow)
    monkeypatch.setattr(server, 'REQUEST_BUDGET_SECONDS', 0.01)
    result = TestClient(app).post('/chat', json={'message': 'test timeout'}).json()
    assert 'too long' in result['response']
    assert result['tool_calls'][0]['name'] == 'plan'


def test_malformed_tool_arguments_allow_researcher_to_continue(monkeypatch):
    count = 0
    async def fake(messages, **kwargs):
        nonlocal count
        count += 1
        if count == 1:
            return {'tool_calls': [{'id': 'c1', 'function': {'name': 'run_sql', 'arguments': '[]'}}]}
        assert json.loads(messages[-1]['content'])['ok'] is False
        return {'content': '{"findings": [], "gaps": ["No valid query"]}'}
    monkeypatch.setattr(llm, 'complete', fake)
    report, calls = asyncio.run(researcher.run(SOURCE, 'count'))
    assert count == 2 and report['evidence'] == [] and calls[0]['agent'] == 'researcher-example'


def test_model_failure_after_query_keeps_executed_evidence(monkeypatch):
    count = 0
    async def fake(messages, **kwargs):
        nonlocal count
        count += 1
        if count == 1:
            return {'tool_calls': [{'id': 'c1', 'function': {'name': 'run_sql',
                                  'arguments': '{"sql": "SELECT 7 AS n"}'}}]}
        raise RuntimeError('provider unavailable')
    monkeypatch.setattr(llm, 'complete', fake)
    report, calls = asyncio.run(researcher.run(SOURCE, 'count'))
    assert report['evidence'][0]['rows'] == [[7]]
    assert any('incomplete' in gap for gap in report['gaps'])
    assert [call['name'] for call in calls] == ['run_sql', 'error']


def test_researcher_turn_cap_keeps_successful_queries(monkeypatch):
    count = 0
    async def fake(messages, **kwargs):
        nonlocal count
        count += 1
        return {'tool_calls': [{'id': str(count), 'function': {'name': 'run_sql',
                               'arguments': '{"sql": "SELECT 7 AS n"}'}}]}
    monkeypatch.setattr(llm, 'complete', fake)
    report, _ = asyncio.run(researcher.run(SOURCE, 'count'))
    assert count == researcher.MAX_TURNS
    assert len(report['evidence']) == researcher.MAX_TURNS
    assert any('Ran out of turns' in gap for gap in report['gaps'])


def test_gap_checker_failure_still_writes_available_evidence(monkeypatch):
    async def fake(messages, tools=None, role='lead'):
        if role == 'writer':
            return {'content': '{"evidence_ids": [1]}'}
        if '"action"' in messages[0]['content']:
            return {'content': '{"action": "research", "tasks": [{"source": "example", "task": "count"}]}'}
        raise RuntimeError('gap checker unavailable')
    async def research(source, task):
        return {'source': source.name, 'gaps': [], 'evidence': [{'source': source.name, 'task': task,
                'sql': 'SELECT 7 AS n', 'columns': ['n'], 'rows': [[7]]}]}, []
    monkeypatch.setattr(llm, 'complete', fake)
    monkeypatch.setattr(researcher, 'run', research)
    monkeypatch.setattr(lead, 'active_sources', lambda: {'example': SOURCE})
    answer, calls = asyncio.run(lead.run('count', []))
    assert '| 7 |' in answer and 'could not complete the gap check' in answer
    assert calls[-1]['agent'] == 'writer'
