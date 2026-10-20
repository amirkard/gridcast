"""HTTP API tests. The agent is replaced by a fake, so no LLM call is made."""

import pytest
from fastapi.testclient import TestClient

import gridcast.agent as agent
from gridcast.main import app

QUESTION = {"question": "How does Elia define total load?"}


def fake_run(question: str, verbose: bool = True, degraded: bool = False) -> dict:
    return {
        "answer": f"echo: {question}",
        "tool_calls": [{"name": "search_docs", "input": {"query": question}}],
        "turns": 2,
    }


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(agent, "run", fake_run)
    with TestClient(app) as c:
        yield c


def test_health_reports_the_model_version(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["model_version"]


def test_ask_is_off_without_a_configured_token(client, monkeypatch):
    """Every call costs money, so no token on the server means no endpoint."""
    monkeypatch.delenv("ASK_TOKEN", raising=False)
    assert client.post("/ask", json=QUESTION).status_code == 503


@pytest.mark.parametrize("headers", [{}, {"X-Ask-Token": "wrong"}])
def test_ask_rejects_a_missing_or_wrong_token(client, monkeypatch, headers):
    monkeypatch.setenv("ASK_TOKEN", "secret")
    assert client.post("/ask", json=QUESTION, headers=headers).status_code == 401


def test_ask_returns_the_answer_and_the_tools_used(client, monkeypatch):
    monkeypatch.setenv("ASK_TOKEN", "secret")
    r = client.post("/ask", json=QUESTION, headers={"X-Ask-Token": "secret"})
    assert r.status_code == 200
    assert r.json() == {
        "answer": f"echo: {QUESTION['question']}",
        "tools": ["search_docs"],
        "turns": 2,
    }


def test_ask_rejects_an_empty_question(client, monkeypatch):
    monkeypatch.setenv("ASK_TOKEN", "secret")
    r = client.post("/ask", json={"question": ""}, headers={"X-Ask-Token": "secret"})
    assert r.status_code == 422
