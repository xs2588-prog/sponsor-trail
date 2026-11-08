"""One place that talks to the model, so tests can swap it out.

Every agent calls `complete()`. Tests monkeypatch it with a fake.
"""

import json
import os
import re

import litellm

DEFAULT_MODEL = os.environ.get("SPONSOR_MODEL", "vertex_ai/gemini-3.5-flash-lite")


def model_for(role: str) -> str:
    """Lead and Writer can use a stronger model via SPONSOR_LEAD_MODEL / SPONSOR_WRITER_MODEL."""
    return os.environ.get(f"SPONSOR_{role.upper()}_MODEL") or DEFAULT_MODEL


async def complete(messages: list[dict], tools: list[dict] | None = None, role: str = "researcher") -> dict:
    """Return the assistant message as a plain dict (content, tool_calls)."""
    kwargs = {"model": model_for(role), "messages": messages, "num_retries": 3}
    if kwargs["model"].startswith("vertex_ai/"):
        kwargs["vertex_location"] = "global"
    if tools:
        kwargs["tools"] = tools
    reply = await litellm.acompletion(**kwargs)
    return reply.choices[0].message.model_dump()


def parse_json(text: str | None) -> dict | None:
    """Pull the first JSON object out of a model reply (it may be wrapped in ```json fences)."""
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        value = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None
