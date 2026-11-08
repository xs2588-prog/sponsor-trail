"""Writer: turns all Researcher findings into one cited answer. Owner: C."""

import json
from datetime import date

from agents import llm

WRITER_PROMPT = """You are the Writer. Researchers queried government data on H-1B and green card
sponsorship and returned findings. Today is {today}. Write the final answer for an international
student, in the same language as their question.

Rules:
- Use ONLY the findings below. Never add numbers or companies from your own memory.
- Put a citation marker like [1] after every number. End with a "Sources" list where each marker
  gives the data source, table, fiscal year and the SQL.
- Where findings from different sources disagree or cannot be linked (e.g. employer names that do
  not match), say so.
- End with a short section on what the data could NOT answer, built from the gaps.
- Keep it short: lead with the direct answer, then a compact table or bullets."""


async def run(question: str, reports: list[dict]) -> str:
    messages = [
        {"role": "system", "content": WRITER_PROMPT.format(today=date.today().isoformat())},
        {"role": "user", "content": f"Question: {question}\n\nFindings:\n{json.dumps(reports, ensure_ascii=False, default=str)}"},
    ]
    reply = await llm.complete(messages, role="writer")
    return reply.get("content") or ""
