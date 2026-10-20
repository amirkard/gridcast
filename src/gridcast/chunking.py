"""Split document text into overlapping chunks for retrieval."""


def _normalize(text: str) -> str:
    """Collapse whitespace inside paragraphs and keep blank lines between them."""
    paragraphs = [" ".join(p.split()) for p in text.split("\n\n")]
    return "\n\n".join(p for p in paragraphs if p)


def _break_point(text: str, start: int, end: int) -> int:
    """Best place to end a chunk in text[start:end]: a paragraph, a sentence, or a word.

    Only the second half of the window is searched, so chunks do not become tiny.
    """
    lo = start + (end - start) // 2
    for sep in ("\n\n", ". ", " "):
        i = text.rfind(sep, lo, end)
        if i != -1:
            return i + len(sep)
    return end


def split_text(text: str, max_chars: int = 1200, overlap: int = 200) -> list[str]:
    """Split text into chunks of at most max_chars characters.

    Chunks end at a paragraph, sentence, or word break where possible, and
    consecutive chunks share up to `overlap` characters, so that a sentence cut
    at a boundary still appears whole in one of them.
    """
    if not 0 <= overlap < max_chars:
        raise ValueError("overlap must be at least 0 and smaller than max_chars")
    text = _normalize(text)
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            end = _break_point(text, start, end)
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        # Step back by the overlap, then forward to the start of a word.
        nxt = max(end - overlap, start + 1)
        space = text.find(" ", nxt, end)
        start = space + 1 if space != -1 else nxt
    return chunks
