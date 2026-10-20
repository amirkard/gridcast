"""Document ingestion tests, with a fake embedder so no model is downloaded."""

from pathlib import Path

from sqlalchemy import text

from gridcast.db import get_engine
from gridcast.embeddings import DIM
from gridcast.ingest_docs import find_files, ingest_document, read_document, to_pgvector

SOURCE = "test://ingest.md"
LONG_TEXT = "\n\n".join(f"Paragraph {i} about measured grid load. " * 12 for i in range(10))


def fake_embed(texts: list[str]) -> list[list[float]]:
    """Deterministic, non-zero vectors of the right size."""
    return [[1.0, (len(t) % 97) / 97] + [0.0] * (DIM - 2) for t in texts]


def _count(conn) -> int:
    q = text("select count(*) from doc_chunks where source = :s")
    return conn.execute(q, {"s": SOURCE}).scalar_one()


def test_ingest_is_idempotent():
    """Running the ingestion twice must not duplicate chunks."""
    with get_engine().connect() as conn:
        tx = conn.begin()
        try:
            first = ingest_document(conn, SOURCE, "Test", [(None, LONG_TEXT)], fake_embed)
            second = ingest_document(conn, SOURCE, "Test", [(None, LONG_TEXT)], fake_embed)
            stored = _count(conn)
        finally:
            tx.rollback()
    assert first == second == stored > 1


def test_empty_document_removes_old_chunks():
    with get_engine().connect() as conn:
        tx = conn.begin()
        try:
            ingest_document(conn, SOURCE, "Test", [(None, LONG_TEXT)], fake_embed)
            n = ingest_document(conn, SOURCE, "Test", [(None, "   ")], fake_embed)
            stored = _count(conn)
        finally:
            tx.rollback()
    assert n == stored == 0


def test_pages_are_kept_per_chunk():
    pages = [(1, "First page text. " * 10), (2, "Second page text. " * 10)]
    with get_engine().connect() as conn:
        tx = conn.begin()
        try:
            ingest_document(conn, SOURCE, "Test", pages, fake_embed)
            q = text("select page from doc_chunks where source = :s order by chunk_index")
            stored = conn.execute(q, {"s": SOURCE}).scalars().all()
        finally:
            tx.rollback()
    assert stored == [1, 2]


def test_markdown_title_is_first_heading(tmp_path: Path):
    doc = tmp_path / "notes.md"
    doc.write_text("Intro line\n\n# Grid notes\n\nBody text.\n", encoding="utf-8")
    title, pages = read_document(doc)
    assert title == "Grid notes"
    assert pages == [(None, doc.read_text(encoding="utf-8"))]


def test_find_files_skips_unsupported_and_underscore_files(tmp_path: Path):
    for name in ("a.md", "b.pdf", "c.txt", "_sources.md", "d.docx"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    names = sorted(p.name for p in find_files([str(tmp_path)]))
    assert names == ["a.md", "b.pdf", "c.txt"]


def test_vector_literal_format():
    assert to_pgvector([1, 0.5, -2.25]) == "[1,0.5,-2.25]"
