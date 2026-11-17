"""Researcher: one per data source, each in a fresh context with only its own tools.

Owner of each source's prompt details: the person who owns that source.
"""

import asyncio
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

Answer the task with SQL. Write all findings and gaps in English. Rules:
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
        try:
            reply = await llm.complete(messages, tools=source.TOOLS, role="researcher")
        except Exception as error:
            tool_calls.append({"agent": agent, "name": "error", "args": {}, "result": type(error).__name__})
            return (ground_report({"gaps": [f"{source.name}: model call failed ({type(error).__name__}); results are incomplete."]},
                                  source.name, task, tool_calls), tool_calls)
        messages.append(reply)
        calls = reply.get("tool_calls") or []
        if not calls:
            report = llm.parse_json(reply.get("content"))
            if report is None:
                report = {"findings": [], "gaps": [f"Researcher did not return JSON: {(reply.get('content') or '')[:200]}"]}
            report = ground_report(report, source.name, task, tool_calls)
            return report, tool_calls

        for call in calls:
            fn = call["function"]
            try:
                args = json.loads(fn.get("arguments") or "{}")
                if not isinstance(args, dict):
                    raise ValueError("Tool arguments must be a JSON object")
                result = await asyncio.to_thread(source.run_tool, fn["name"], args)
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                args, result = {}, json.dumps({"ok": False, "error": f"Arguments were not valid JSON: {e}"})
            tool_calls.append({"agent": agent, "name": fn["name"], "args": args, "result": result})
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})

    return (ground_report({"findings": [],
             "gaps": [f"Ran out of turns ({MAX_TURNS}) before finishing."]},
             source.name, task, tool_calls), tool_calls)


def ground_report(report: dict, source: str, task: str, calls: list[dict]) -> dict:
    """Only executed, successful SQL results can enter the evidence sent to the Writer."""
    evidence = []
    for call in calls:
        try:
            result = json.loads(call["result"])
        except (ValueError, TypeError):
            continue
        if call["name"] == "run_sql" and result.get("ok") is True:
            evidence.append({"source": source, "task": task, "sql": result["sql"],
                             "columns": result["columns"], "rows": result["rows"],
                             "truncated": result.get("truncated", False)})
    gaps = report.get("gaps", [])
    gaps = [g for g in gaps if isinstance(g, str)] if isinstance(gaps, list) else []
    findings = []
    proposed = report.get("findings", [])
    for finding in proposed if isinstance(proposed, list) else []:
        if not isinstance(finding, dict) or not isinstance(finding.get("citation"), dict):
            continue
        raw_sql = finding["citation"].get("sql")
        sql = raw_sql.strip().rstrip(";") if isinstance(raw_sql, str) else ""
        match = next((e for e in evidence if e["sql"] == sql), None)
        # Finding prose remains a model interpretation. The Writer receives raw evidence only.
        if match and any(str(finding.get("value")) == str(cell) for row in match["rows"] for cell in row):
            findings.append(finding)
        else:
            gaps.append("Discarded a finding whose SQL or value did not match a successful query.")
    if not evidence:
        gaps.append(f"{source}: no successful SQL query was executed; no claims are supported.")
    return {"source": source, "task": task, "findings": findings,
            "evidence": evidence, "gaps": list(dict.fromkeys(gaps))}
