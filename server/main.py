"""Web server. /chat keeps Project 1's response shape: response, session_id, tool_calls.

Each tool_calls entry also has an `agent` field: lead, researcher-<source> or writer.
"""

import asyncio
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from agents import lead, llm
from sources import active_sources

REQUEST_BUDGET_SECONDS = 270  # graders wait up to 5 minutes; Cloud Run timeout must be >= 300s
FRONTEND = Path(__file__).resolve().parent.parent / "frontend" / "index.html"

app = FastAPI(title="Sponsor Trail")

# session_id -> list of {role, content} turns. In-memory, single process.
sessions: dict[str, list[dict]] = {}


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    session_id: str
    tool_calls: list[dict]


def describe_model_error(e: Exception) -> str:
    """One readable line plus how to fix it, instead of a provider traceback."""
    detail = (str(e).strip().splitlines() or [type(e).__name__])[0][:300]
    text = str(e).lower()
    if "credentials" in text:
        hint = "Run `gcloud auth application-default login`, then restart the server."
    elif "billing" in text or "permission" in text or "403" in text:
        hint = "Check that the GCP project has billing and the Vertex AI API enabled."
    elif "connection" in text or "timed out" in text:
        hint = "Network problem reaching the model. Try again."
    else:
        hint = "Check the server log for details."
    return f"Model call failed: {type(e).__name__}: {detail}\n{hint}"


@app.get("/")
def index():
    return FileResponse(FRONTEND, headers={"Cache-Control": "no-store, max-age=0"})


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    session_id = request.session_id or str(uuid.uuid4())
    history = sessions.setdefault(session_id, [])
    try:
        response, tool_calls = await asyncio.wait_for(
            lead.run(request.message, history), timeout=REQUEST_BUDGET_SECONDS)
    except asyncio.TimeoutError:
        response, tool_calls = "Sorry, this question took too long. Try narrowing the job, place or years.", []
    except Exception as e:  # auth, billing, model down: show it in the chat, not as a 500
        response, tool_calls = describe_model_error(e), []
    history += [{"role": "user", "content": request.message}, {"role": "assistant", "content": response}]
    return ChatResponse(response=response, session_id=session_id, tool_calls=tool_calls)


@app.post("/clear")
def clear(session_id: str | None = None):
    sessions.pop(session_id, None)
    return {"status": "ok"}


@app.get("/api/status")
def status():
    """Which sources are loaded, so the UI can show them."""
    return {
        "model": llm.DEFAULT_MODEL,
        "sources": [{"name": n, "description": s.description} for n, s in active_sources().items()],
    }
