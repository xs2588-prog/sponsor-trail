"""The contract every data source follows, plus a ready-made SQL source.

A source module exposes one object, SOURCE, with:
    name          short id, e.g. "lca" (the Researcher is called researcher-<name>)
    description   one paragraph: what this data can and can't answer. The Lead reads it
                  to decide which Researcher gets which question.
    schema_doc    the data dictionary the Researcher sees: tables, columns, example values, pitfalls
    available()   True when the data files exist
    TOOLS         OpenAI/LiteLLM tool declarations
    run_tool(name, args) -> str   JSON string, never raises

A Researcher must end with this JSON (see agents/researcher.py):
    {"source": "lca",
     "findings": [{"claim": "...", "value": 123,
                   "citation": {"table": "lca", "fiscal_year": 2025, "sql": "SELECT ..."}}],
     "gaps": ["what this data could not answer"]}
"""

import json
import os
import re
import threading
from pathlib import Path

import duckdb

MAX_ROWS = 50
DATA_DIR = os.environ.get(
    "SPONSOR_DATA_DIR", str(Path(__file__).resolve().parent.parent / "data" / "clean")
)

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|create|alter|attach|detach|copy|export|install|load|pragma|call|set)\b",
    re.IGNORECASE,
)


def data_path(filename: str) -> str:
    """Where a cleaned file lives. B decides whether DATA_DIR is local or downloaded from GCS at startup."""
    return str(Path(DATA_DIR) / filename)


class SqlSource:
    """A source backed by one or more files (parquet or csv) queried with DuckDB."""

    def __init__(self, name: str, description: str, tables: dict[str, str], schema_doc: str):
        self.name = name
        self.description = description
        self.tables = tables  # table name -> file path
        self.schema_doc = schema_doc
        self._con = None
        self._lock = threading.Lock()

    # --- contract ---

    def available(self) -> bool:
        return all(Path(p).exists() for p in self.tables.values())

    @property
    def TOOLS(self) -> list[dict]:
        return [{
            "type": "function",
            "function": {
                "name": "run_sql",
                "description": (
                    f"Run one read-only DuckDB SELECT over the {self.name} tables "
                    f"({', '.join(self.tables)}). Returns at most {MAX_ROWS} rows. "
                    "Aggregate in SQL (GROUP BY, COUNT, MEDIAN) instead of pulling raw rows."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"sql": {"type": "string", "description": "A single SELECT statement."}},
                    "required": ["sql"],
                },
            },
        }]

    def run_tool(self, name: str, args: dict) -> str:
        if name != "run_sql":
            return json.dumps({"ok": False, "error": f"Unknown tool {name}"})
        return json.dumps(self.run_sql(args.get("sql", "")), default=str)

    # --- SQL ---

    def _connection(self):
        if self._con is None:
            con = duckdb.connect()
            for table, path in self.tables.items():
                reader = "read_parquet" if path.endswith(".parquet") else "read_csv_auto"
                con.execute(f"CREATE VIEW {table} AS SELECT * FROM {reader}('{path}')")
            self._con = con
        return self._con

    def run_sql(self, sql: str) -> dict:
        sql = (sql or "").strip().rstrip(";")
        if not re.match(r"^(select|with)\b", sql, re.IGNORECASE) or ";" in sql or _FORBIDDEN.search(sql):
            return {"ok": False, "error": "Only a single read-only SELECT is allowed.",
                    "fix": "Rewrite as one SELECT (or WITH ... SELECT) statement."}
        try:
            with self._lock:  # one DuckDB connection per source, shared across requests
                cur = self._connection().execute(sql)
                columns = [d[0] for d in cur.description]
                rows = cur.fetchmany(MAX_ROWS + 1)
        except Exception as e:  # SQL errors go back to the model so it can fix the query
            return {"ok": False, "error": str(e).splitlines()[0][:400],
                    "fix": "Check table and column names against the data dictionary and retry."}
        return {"ok": True, "columns": columns, "rows": [list(r) for r in rows[:MAX_ROWS]],
                "truncated": len(rows) > MAX_ROWS, "sql": sql}
