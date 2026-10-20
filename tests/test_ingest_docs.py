"""Document ingestion tests, with a fake embedder so no model is downloaded."""

from pathlib import Path

from sqlalchemy import text

from gridcast.db import get_engine
from gridcast.embeddings import DIM
from gridcast.ingest_docs import find_files, ingest_document, prune, read_document, to_pgvector

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
            first = ingest_document(conn, SOURCE, "Test", [(None, LONG_TEXT)], fake_embed).stored
            second = ingest_document(conn, SOURCE, "Test", [(None, LONG_TEXT)], fake_embed).stored
            stored = _count(conn)
        finally:
            tx.rollback()
    assert first == second == stored > 1


def test_empty_document_removes_old_chunks():
    with get_engine().connect() as conn:
        tx = conn.begin()
        try:
            ingest_document(conn, SOURCE, "Test", [(None, LONG_TEXT)], fake_embed)
            n = ingest_document(conn, SOURCE, "Test", [(None, "   ")], fake_embed).stored
            stored = _count(conn)
        finally:
            tx.rollback()
    assert n == stored == 0


def test_pages_are_kept_per_chunk():
    pages = [(1, "First page text, with several words. " * 5),
             (2, "Second page text, with several words. " * 5)]
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


def test_noise_chunks_are_skipped():
    """A chart axis (numbers and labels) is dropped; the real paragraph is kept."""
    axis = "Hours MW 00 01 02 03 04 05 06 07 08 09 10 11 12 0 2000 4000 6000 8000 10 000"
    prose = "The total load is an estimate of the electricity consumption in Belgium. " * 2
    with get_engine().connect() as conn:
        tx = conn.begin()
        try:
            result = ingest_document(conn, SOURCE, "Test", [(1, axis), (2, prose)], fake_embed)
            q = text("select page from doc_chunks where source = :s")
            pages = conn.execute(q, {"s": SOURCE}).scalars().all()
        finally:
            tx.rollback()
    assert (result.stored, result.skipped) == (1, 1)
    assert pages == [2]


def test_prune_removes_documents_no_longer_in_the_library():
    with get_engine().connect() as conn:
        tx = conn.begin()
        try:
            current = conn.execute(text("select distinct source from doc_chunks")).scalars().all()
            ingest_document(conn, "gone.md", "Gone", [(None, LONG_TEXT)], fake_embed)
            removed = prune(conn, current)
            left = conn.execute(
                text("select count(*) from doc_chunks where source = 'gone.md'")
            ).scalar_one()
        finally:
            tx.rollback()
    assert removed > 0
    assert left == 0
