"""Load documents into doc_chunks, with one embedding per chunk.

Usage:
    uv run python -m gridcast.ingest_docs                 # README.md, NOTES.md, corpus/
    uv run python -m gridcast.ingest_docs corpus/x.pdf    # specific files or folders

Re-running replaces the chunks of each document, so the table always matches
the files. Supported formats: .md, .txt, .pdf. Files whose names start with "_"
are skipped (corpus/_sources.md lists the documents to download).
"""

import sys
from collections.abc import Callable, Iterable
from pathlib import Path

from sqlalchemy import Connection, text

from gridcast.chunking import split_text
from gridcast.db import get_engine

EmbedFn = Callable[[list[str]], list[list[float]]]
Pages = list[tuple[int | None, str]]

SUPPORTED = {".md", ".txt", ".pdf"}
DEFAULT_PATHS = ["README.md", "NOTES.md", "corpus"]

INSERT = text(
    "insert into doc_chunks (source, title, page, chunk_index, content, embedding) "
    "values (:source, :title, :page, :chunk_index, :content, cast(:embedding as vector))"
)


def to_pgvector(values: Iterable[float]) -> str:
    """Format a vector as a pgvector text literal."""
    return "[" + ",".join(f"{float(v):.7g}" for v in values) + "]"


def read_document(path: Path) -> tuple[str, Pages]:
    """Return the document title and its text as (page, text) pairs.

    PDF pages are numbered from 1. Text files have one part with page None.
    """
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(path)
        meta_title = reader.metadata.title if reader.metadata else None
        title = (meta_title or path.stem).strip() or path.stem
        pages: Pages = [(i, p.extract_text() or "") for i, p in enumerate(reader.pages, 1)]
        return title, pages

    content = path.read_text(encoding="utf-8")
    headings = (line.lstrip("#").strip() for line in content.splitlines() if line.startswith("#"))
    title = next(headings, "") or path.stem
    return title, [(None, content)]


def ingest_document(
    conn: Connection, source: str, title: str, pages: Pages, embed: EmbedFn
) -> int:
    """Replace the chunks of one source. Returns the number of chunks stored."""
    pieces = [(page, piece) for page, body in pages for piece in split_text(body)]
    conn.execute(text("delete from doc_chunks where source = :source"), {"source": source})
    if not pieces:
        return 0

    vectors = embed([piece for _, piece in pieces])
    rows = [
        {
            "source": source,
            "title": title,
            "page": page,
            "chunk_index": i,
            "content": piece,
            "embedding": to_pgvector(vector),
        }
        for i, ((page, piece), vector) in enumerate(zip(pieces, vectors, strict=True))
    ]
    conn.execute(INSERT, rows)
    return len(rows)


def find_files(paths: Iterable[str]) -> list[Path]:
    """Expand files and folders into the supported documents they contain."""
    found: list[Path] = []
    for raw in paths:
        p = Path(raw)
        candidates = sorted(p.rglob("*")) if p.is_dir() else [p]
        found += [
            c for c in candidates
            if c.is_file() and c.suffix.lower() in SUPPORTED and not c.name.startswith("_")
        ]
    return found


def main(argv: list[str]) -> int:
    from gridcast.embeddings import embed_passages

    files = find_files(argv[1:] or DEFAULT_PATHS)
    if not files:
        print("No documents found. Put .md, .txt or .pdf files in corpus/.")
        return 1

    total = 0
    with get_engine().begin() as conn:
        for path in files:
            title, pages = read_document(path)
            n = ingest_document(conn, path.as_posix(), title, pages, embed_passages)
            total += n
            print(f"{n:5d} chunks  {path.as_posix()}  ({title})")
    print(f"{total:5d} chunks in total")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
