import json

from sources import active_sources
from sources.example import SOURCE


def test_example_source_is_active_and_queryable():
    assert "example" in active_sources()
    out = SOURCE.run_sql("SELECT employer_key, COUNT(*) AS n FROM example_lca GROUP BY 1 ORDER BY n DESC")
    assert out["ok"] and out["rows"][0] == ["acme analytics", 3]


def test_sql_tool_is_read_only():
    for bad in ["DROP VIEW example_lca", "SELECT 1; DROP VIEW example_lca", "COPY example_lca TO 'x.csv'"]:
        assert SOURCE.run_sql(bad)["ok"] is False


def test_sql_errors_come_back_as_json():
    result = json.loads(SOURCE.run_tool("run_sql", {"sql": "SELECT nope FROM example_lca"}))
    assert result["ok"] is False and "fix" in result
