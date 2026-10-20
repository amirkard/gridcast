"""Split document text into overlapping chunks for retrieval."""

import re

# Four or more number-like tokens in a row: chart axes, tick labels, table grids.
_NUMBER_RUN = re.compile(r"(?<!\S)(?:\d[\d.,:/-]*\s+){3,}\d[\d.,:/-]*(?!\S)")


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


def is_informative(chunk: str, min_letter_ratio: float = 0.5, min_words: int = 8) -> bool:
    """False for chunks that are mostly numbers or labels, such as chart axes or menus.

    A chunk passes when at least `min_letter_ratio` of its non-space characters
    are letters and it has at least `min_words` words of three or more letters.
    """
    chars = [c for c in chunk if not c.isspace()]
    if not chars:
        return False
    letters = sum(c.isalpha() for c in chars)
    words = [w for w in chunk.split() if sum(c.isalpha() for c in w) >= 3]
    return letters / len(chars) >= min_letter_ratio and len(words) >= min_words


def strip_number_runs(text: str) -> str:
    """Remove runs of four or more number-like tokens, such as chart axis labels.

    Text extracted from a web page saved as PDF contains axis ticks like
    "00 01 02 03 ... 2000 4000 6000". They carry no meaning for retrieval, but
    they make a chunk look like a match for many queries.
    """
    return _NUMBER_RUN.sub(" ", text)
