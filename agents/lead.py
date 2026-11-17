"""Lead: clarifies, plans, fans out to Researchers in parallel, fills gaps, hands off to the Writer. Owner: A."""

import asyncio
import json
from datetime import date

from agents import llm, researcher, writer
from sources import active_sources

MAX_GAP_ROUNDS = 2  # extra rounds after the first fan-out
MAX_TASKS_PER_ROUND = 6

PLAN_PROMPT = """You are the Lead of a research team that answers questions about which US employers
sponsor H-1B visas and green cards, for international students. Write all messages and tasks in English. Today is {today}
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
  "message": "<clarifying question or refusal, in English; empty for research>",
  "resolved_question": "<complete question incorporating all earlier clarifications, in English>",
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
    valid = [t for t in tasks if isinstance(t, dict) and isinstance(t.get("source"), str) and t.get("source") in sources
             and isinstance(t.get("task"), str) and t["task"].strip()][:MAX_TASKS_PER_ROUND]
    tool_calls.append({"agent": "lead", "name": "dispatch_researchers",
                       "args": {"tasks": valid}, "result": f"{len(valid)} researchers started in parallel"})
    results = await asyncio.gather(*(researcher.run(sources[t["source"]], t["task"]) for t in valid),
                                   return_exceptions=True)
    reports = []
    for task, result in zip(valid, results):
        if isinstance(result, BaseException):
            reports.append({"source": task["source"], "task": task["task"], "findings": [],
                            "evidence": [], "gaps": [f"Researcher failed ({type(result).__name__}); this source is incomplete."]})
            tool_calls.append({"agent": f"researcher-{task['source']}", "name": "error", "args": {},
                               "result": type(result).__name__})
        else:
            report, calls = result
            reports.append(report)
            tool_calls.extend(calls)
    return reports


async def run(question: str, history: list[dict], trace: list[dict] | None = None) -> tuple[str, list[dict]]:
    """Answer one user turn. history = earlier {role, content} turns (for clarifications)."""
    sources = active_sources()
    tool_calls: list[dict] = trace if trace is not None else []
    if not sources:
        return "No data sources are loaded yet, so I can't research this.", tool_calls

    today = date.today()
    plan_messages = [
        {"role": "system", "content": PLAN_PROMPT.format(
            today=today.isoformat(), last_year=today.year - 1, sources=_sources_block(sources))},
        *history[-12:],
        {"role": "user", "content": question},
    ]
    plan = llm.parse_json((await llm.complete(plan_messages, role="lead")).get("content")) or {}
    tool_calls.append({"agent": "lead", "name": "plan", "args": {"question": question},
                       "result": json.dumps(plan, ensure_ascii=False)})

    action = plan.get("action")
    if action != "research" or not isinstance(plan.get("tasks"), list) or not plan["tasks"]:
        message = plan.get("message")
        return (message if isinstance(message, str) and message.strip() else
                "Could you tell me which job and which years you're interested in?"), tool_calls

    resolved = plan.get("resolved_question")
    if not isinstance(resolved, str) or not resolved.strip():
        resolved = question
    # Preserve the literal conversation too: a malformed/incomplete rewrite must not erase it.
    context = "\n".join(f"{m['role']}: {m['content']}" for m in history[-12:])
    research_question = f"{resolved}\n\nConversation context:\n{context}\nuser: {question}"
    reports = await _fan_out(plan["tasks"], sources, tool_calls)

    for _ in range(MAX_GAP_ROUNDS):
        gap_messages = [
            {"role": "system", "content": GAP_PROMPT.format(names=", ".join(sources))},
            {"role": "user", "content": f"Question: {research_question}\n\nFindings:\n"
                                        f"{json.dumps(reports, ensure_ascii=False, default=str)}"},
        ]
        try:
            check = llm.parse_json((await llm.complete(gap_messages, role="lead")).get("content"))
        except Exception:
            check = None
        if check is None:
            reports.append({"source": "lead", "evidence": [], "gaps": [
                "The Lead could not complete the gap check; the available results may be incomplete."]})
            tool_calls.append({"agent": "lead", "name": "check_gaps", "args": {}, "result": '{"error": "gap check unavailable"}'})
            break
        tool_calls.append({"agent": "lead", "name": "check_gaps", "args": {},
                           "result": json.dumps(check, ensure_ascii=False)})
        if check.get("done", True) or not isinstance(check.get("tasks"), list) or not check["tasks"]:
            break
        reports += await _fan_out(check["tasks"], sources, tool_calls)
    else:
        reports.append({"source": "lead", "evidence": [], "gaps": [
            f"Reached the follow-up cap ({MAX_GAP_ROUNDS} extra rounds); some questions may remain unresolved."]})

    if "example" in sources:
        reports.append({"source": "example", "evidence": [], "gaps": [
            "TOY DEMO ONLY: all companies and numbers in the example source are fabricated, not government evidence."]})
    for name in ("lca", "uscis", "perm"):
        if name not in sources:
            reports.append({"source": name, "evidence": [], "gaps": [f"{name} data is not loaded; this source cannot be checked."]})
    answer = await writer.run(research_question, reports)
    tool_calls.append({"agent": "writer", "name": "write_report",
                       "args": {"reports": len(reports)}, "result": "ok"})
    return answer, tool_calls
