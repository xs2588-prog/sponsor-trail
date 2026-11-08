"""End-to-end /chat with a fake model: plan -> parallel researchers -> gap check -> writer."""

import json

from fastapi.testclient import TestClient

from agents import llm
from server.main import app


def fake_model(script):
    async def complete(messages, tools=None, role="researcher"):
        system = messages[0]["content"]
        if role == "lead" and "Reply with ONLY JSON:\n{\"action\"" in system:
            return {"content": json.dumps(script["plan"])}
        if role == "lead":
            return {"content": json.dumps({"done": True})}
        if role == "writer":
            return {"content": "Acme Analytics filed the most [1]."}
        # researcher: first run SQL, then report
        if not any(m.get("role") == "tool" for m in messages):
            return {"content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {
                "name": "run_sql", "arguments": json.dumps({"sql": "SELECT COUNT(*) FROM example_lca"})}}]}
        return {"content": json.dumps({"findings": [{"claim": "7 filings", "value": 7,
                "citation": {"table": "example_lca", "fiscal_year": "2024-2025", "sql": "SELECT COUNT(*) FROM example_lca"}}],
                "gaps": []})}
    return complete


def test_chat_shape_and_agent_field(monkeypatch):
    plan = {"action": "research", "message": "",
            "tasks": [{"source": "example", "task": "count filings"}, {"source": "example", "task": "top employer"}]}
    monkeypatch.setattr(llm, "complete", fake_model({"plan": plan}))
    data = TestClient(app).post("/chat", json={"message": "who files most?"}).json()

    assert set(data) == {"response", "session_id", "tool_calls"}
    assert "[1]" in data["response"]
    agents = [c["agent"] for c in data["tool_calls"]]
    assert agents[0] == "lead" and agents[-1] == "writer"
    assert agents.count("researcher-example") == 2  # two researchers ran
    assert all({"agent", "name", "args", "result"} <= set(c) for c in data["tool_calls"])


def test_vague_question_gets_clarification(monkeypatch):
    plan = {"action": "clarify", "message": "Which job and which years?", "tasks": []}
    monkeypatch.setattr(llm, "complete", fake_model({"plan": plan}))
    data = TestClient(app).post("/chat", json={"message": "good visa jobs?"}).json()
    assert data["response"] == "Which job and which years?"
    assert [c["name"] for c in data["tool_calls"]] == ["plan"]
