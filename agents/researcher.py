"""Researcher: one per data source, each in a fresh context with only its own tools.

Owner of each source's prompt details: the person who owns that source.
"""

import json
from datetime import date

from agents import llm
from sources.base import SqlSource

MAX_TURNS = 6

RESEARCHER_PROMPT = """You are the {name} Researcher in a team that studies which US employers sponsor
H-1B visas and green cards. You can only see the {name} data. Today is {today}.

What this data is:
{description}

Data dictionary:
{schema_doc}

Answer the task with SQL. Rules:
- Aggregate in SQL; never guess numbers. Every number you report must come from a query you ran.
- Fiscal year (FY) runs October to September: FY2025 = Oct 2024 to Sep 2025. Say which kind of year you used.
- If a query errors, read the error and fix the query.
- If the data cannot answer part of the task, say so in "gaps" instead of guessing.

When done, reply with ONLY this JSON:
{{"source": "{name}",
  "findings": [{{"claim": "one sentence", "value": <number or short text>,
                "citation": {{"table": "<table>", "fiscal_year": "<FY or range>", "sql": "<the SQL you ran>"}}}}],
  "gaps": ["what this data could not answer"]}}"""


async def run(source: SqlSource, task: str) -> tuple[dict, list[dict]]:
    """Run one Researcher on one task. Returns (report, tool_calls)."""
    agent = f"researcher-{source.name}"
    messages = [
        {"role": "system", "content": RESEARCHER_PROMPT.format(
            name=source.name, today=date.today().isoformat(),
            description=source.description, schema_doc=source.schema_doc)},
        {"role": "user", "content": task},
    ]
    tool_calls: list[dict] = []

    for _ in range(MAX_TURNS):
        reply = await llm.complete(messages, tools=source.TOOLS, role="researcher")
        messages.append(reply)
        calls = reply.get("tool_calls") or []
        if not calls:
            report = llm.parse_json(reply.get("content"))
            if report is None:
                report = {"findings": [], "gaps": [f"Researcher did not return JSON: {(reply.get('content') or '')[:200]}"]}
            report["source"] = source.name
            report.setdefault("findings", [])
            report.setdefault("gaps", [])
            return report, tool_calls

        for call in calls:
            fn = call["function"]
            try:
                args = json.loads(fn.get("arguments") or "{}")
                result = source.run_tool(fn["name"], args)
            except json.JSONDecodeError as e:
                args, result = {}, json.dumps({"ok": False, "error": f"Arguments were not valid JSON: {e}"})
            tool_calls.append({"agent": agent, "name": fn["name"], "args": args, "result": result})
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})

    return ({"source": source.name, "findings": [],
             "gaps": [f"Ran out of turns ({MAX_TURNS}) before finishing."]}, tool_calls)
