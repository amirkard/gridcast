"""Retrieval schema tests: pgvector is installed and nearest-neighbour search works."""

from sqlalchemy import text

from gridcast.db import get_engine

DIM = 384


def _vec(*head: float) -> str:
    """A DIM-long vector literal that starts with the given values."""
    values = list(head) + [0.0] * (DIM - len(head))
    return "[" + ",".join(str(v) for v in values) + "]"


def test_vector_extension_installed():
    with get_engine().connect() as c:
        n = c.execute(text("select count(*) from pg_extension where extname = 'vector'"))
        assert n.scalar_one() == 1


def test_nearest_neighbour_orders_by_cosine_distance():
    """Insert two chunks, query close to one of them, then roll back."""
    insert = text(
        "insert into doc_chunks (source, title, page, chunk_index, content, embedding) "
        "values (:source, :title, null, 0, :content, cast(:embedding as vector))"
    )
    query = text(
        "select source from doc_chunks where source like 'test://%' "
        "order by embedding <=> cast(:q as vector) limit 2"
    )
    with get_engine().connect() as c:
        tx = c.begin()
        try:
            c.execute(insert, [
                {"source": "test://near", "title": "near", "content": "near",
                 "embedding": _vec(1.0)},
                {"source": "test://far", "title": "far", "content": "far",
                 "embedding": _vec(0.0, 1.0)},
            ])
            sources = c.execute(query, {"q": _vec(0.9, 0.1)}).scalars().all()
        finally:
            tx.rollback()
    assert sources == ["test://near", "test://far"]
