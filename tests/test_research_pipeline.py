"""Regression tests for source availability and SQL isolation."""
import asyncio
import json
from fastapi.testclient import TestClient
from agents import lead, llm, researcher, writer
from server.main import app
from sources.base import SqlSource
from sources.example import SOURCE


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


def test_required_sources_fail_startup(monkeypatch):
    monkeypatch.setenv('SPONSOR_REQUIRED_SOURCES', 'lca,uscis,perm')
    monkeypatch.delenv('SPONSOR_GCS_URI', raising=False)
    import pytest
    with pytest.raises(RuntimeError, match='Required data sources missing'):
        with TestClient(app):
            pass


def test_sql_parser_allows_keywords_inside_literals_but_rejects_mutation():
    assert SOURCE.run_sql("SELECT 'update; set' AS text")['rows'] == [['update; set']]
    assert not SOURCE.run_sql('WITH c AS (SELECT 1) DELETE FROM example_lca')['ok']
    assert not SOURCE.run_sql('SELECT 1; SELECT 2')['ok']
    assert not SOURCE.run_sql(['SELECT 1'])['ok']
