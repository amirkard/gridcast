"""search_docs contract tests, with a fake query embedder so no model is downloaded."""

import json

import pytest
from sqlalchemy import text

from gridcast import embeddings
from gridcast.db import get_engine
from gridcast.embeddings import DIM
from gridcast.ingest_docs import INSERT, to_pgvector
from gridcast.tools import search_docs

ALPHA = [1.0, 0.0] + [0.0] * (DIM - 2)
BETA = [0.0, 1.0] + [0.0] * (DIM - 2)


@pytest.fixture(autouse=True)
def two_chunks(monkeypatch):
    """Two committed test chunks, removed afterwards; queries embed to one of them."""
    rows = [
        {"source": "test://search/alpha.pdf", "title": "Alpha", "page": 3, "chunk_index": 0,
         "content": "Alpha passage.", "embedding": to_pgvector(ALPHA)},
        {"source": "test://search/beta.md", "title": "Beta", "page": None, "chunk_index": 0,
         "content": "Beta passage.", "embedding": to_pgvector(BETA)},
    ]
    with get_engine().begin() as c:
        c.execute(INSERT, rows)
    monkeypatch.setattr(embeddings, "embed_query", lambda q: ALPHA if "alpha" in q else BETA)
    yield
    with get_engine().begin() as c:
        c.execute(text("delete from doc_chunks where source like 'test://search/%'"))


def test_closest_passage_comes_first():
    top = search_docs("an alpha question")["results"][0]
    assert top["source"] == "test://search/alpha.pdf"
    assert top["score"] == pytest.approx(1.0)


def test_results_carry_title_and_page():
    top = search_docs("a beta question")["results"][0]
    assert (top["title"], top["page"], top["text"]) == ("Beta", None, "Beta passage.")


def test_result_is_json_serialisable():
    json.dumps(search_docs("an alpha question"))


@pytest.mark.parametrize(("k", "most"), [(0, 1), (2, 2), (50, 10)])
def test_k_is_clamped(k, most):
    results = search_docs("an alpha question", k=k)["results"]
    assert 1 <= len(results) <= most


def test_empty_query_is_rejected():
    out = search_docs("   ")
    assert "error" in out
    assert "results" not in out
