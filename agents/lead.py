"""Lead: clarifies, plans, fans out to Researchers in parallel, fills gaps, hands off to the Writer. Owner: A."""

import asyncio
import json
from datetime import date

from agents import llm, researcher, writer
from sources import active_sources

MAX_GAP_ROUNDS = 2  # extra rounds after the first fan-out

PLAN_PROMPT = """You are the Lead of a research team that answers questions about which US employers
sponsor H-1B visas and green cards, for international students. Today is {today}
("last year" = {last_year}).

Your Researchers, one per data source:
{sources}

Decide one of:
1. The question is too vague to research (no job/occupation, or no sense of what they want to know,
   or a time range that could mean several things). Ask ONE short clarifying question.
2. The question is outside what these sources can answer at all. Say so briefly.
3. Otherwise, split it into tasks. Give each Researcher a self-contained task (it sees nothing else):
   include the job (with SOC code if you know it), place, years, and exactly what numbers to return.
   Use several Researchers when the question links their data (e.g. LCA filers -> USCIS approvals -> PERM).

Reply with ONLY JSON:
{{"action": "clarify" | "refuse" | "research",
  "message": "<clarifying question or refusal, in the user's language; empty for research>",
  "tasks": [{{"source": "<name>", "task": "<task>"}}]}}"""

GAP_PROMPT = """You are the Lead. Here is the user's question and what the Researchers found so far.
Is anything needed to answer the question still missing that a Researcher could get with one more
focused task (e.g. a follow-up lookup of the companies another source found)? Do not ask again for
things a Researcher already said its data cannot answer.

Reply with ONLY JSON: {{"done": true}} or {{"done": false, "tasks": [{{"source": "<name>", "task": "<task>"}}]}}
Available sources: {names}"""


def _sources_block(sources) -> str:
    return "\n".join(f"- {name}: {s.description}" for name, s in sources.items())


async def _fan_out(tasks: list[dict], sources, tool_calls: list[dict]) -> list[dict]:
    """Run every valid task at once; each Researcher starts with a fresh context."""
    valid = [t for t in tasks if t.get("source") in sources and t.get("task")]
    tool_calls.append({"agent": "lead", "name": "dispatch_researchers",
                       "args": {"tasks": valid}, "result": f"{len(valid)} researchers started in parallel"})
    results = await asyncio.gather(*(researcher.run(sources[t["source"]], t["task"]) for t in valid))
    reports = []
    for report, calls in results:
        reports.append(report)
        tool_calls.extend(calls)
    return reports


async def run(question: str, history: list[dict]) -> tuple[str, list[dict]]:
    """Answer one user turn. history = earlier {role, content} turns (for clarifications)."""
    sources = active_sources()
    tool_calls: list[dict] = []
    if not sources:
        return "No data sources are loaded yet, so I can't research this.", tool_calls

    today = date.today()
    plan_messages = [
        {"role": "system", "content": PLAN_PROMPT.format(
            today=today.isoformat(), last_year=today.year - 1, sources=_sources_block(sources))},
        *history[-6:],
        {"role": "user", "content": question},
    ]
    plan = llm.parse_json((await llm.complete(plan_messages, role="lead")).get("content")) or {}
    tool_calls.append({"agent": "lead", "name": "plan", "args": {"question": question},
                       "result": json.dumps(plan, ensure_ascii=False)})

    action = plan.get("action")
    if action in ("clarify", "refuse") or not plan.get("tasks"):
        return plan.get("message") or "Could you tell me which job and which years you're interested in?", tool_calls

    reports = await _fan_out(plan["tasks"], sources, tool_calls)

    for _ in range(MAX_GAP_ROUNDS):
        gap_messages = [
            {"role": "system", "content": GAP_PROMPT.format(names=", ".join(sources))},
            {"role": "user", "content": f"Question: {question}\n\nFindings:\n"
                                        f"{json.dumps(reports, ensure_ascii=False, default=str)}"},
        ]
        check = llm.parse_json((await llm.complete(gap_messages, role="lead")).get("content")) or {"done": True}
        tool_calls.append({"agent": "lead", "name": "check_gaps", "args": {},
                           "result": json.dumps(check, ensure_ascii=False)})
        if check.get("done", True) or not check.get("tasks"):
            break
        reports += await _fan_out(check["tasks"], sources, tool_calls)

    answer = await writer.run(question, reports)
    tool_calls.append({"agent": "writer", "name": "write_report",
                       "args": {"reports": len(reports)}, "result": "ok"})
    return answer, tool_calls
