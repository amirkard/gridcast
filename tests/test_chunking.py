"""Chunking tests. Pure functions: no database or model needed."""

import random
from itertools import pairwise

import pytest

from gridcast.chunking import is_informative, split_text, strip_number_runs

WORDS = ["grid", "load", "Belgium", "forecast.", "measured", "Elia", "temperature", "interval"]


def _document(seed: int = 1, paragraphs: int = 15) -> str:
    rng = random.Random(seed)
    return "\n\n".join(
        " ".join(rng.choice(WORDS) for _ in range(rng.randint(20, 120)))
        for _ in range(paragraphs)
    )


def _normalized(text: str) -> str:
    return "\n\n".join(" ".join(p.split()) for p in text.split("\n\n") if p.strip())


def test_short_text_is_one_chunk():
    assert split_text("  short   text\n\nhere ") == ["short text\n\nhere"]


def test_empty_text_gives_no_chunks():
    assert split_text("   \n\n  ") == []


def test_chunks_respect_the_size_limit():
    assert all(len(c) <= 1200 for c in split_text(_document()))


def test_chunks_cover_the_whole_text():
    """Every non-space character of the document is in at least one chunk."""
    text = _normalized(_document())
    covered = [False] * len(text)
    for chunk in split_text(text):
        i = text.find(chunk)
        assert i != -1
        covered[i : i + len(chunk)] = [True] * len(chunk)
    assert all(c or text[k].isspace() for k, c in enumerate(covered))


def test_chunks_never_start_in_the_middle_of_a_word():
    text = _normalized(_document(seed=2))
    for chunk in split_text(text):
        i = text.find(chunk)
        assert i == 0 or text[i - 1] in " \n"


def test_consecutive_chunks_overlap():
    chunks = split_text(_document(seed=3))
    assert len(chunks) > 2
    for a, b in pairwise(chunks):
        assert any(word in b[:250] for word in a[-200:].split())


def test_overlap_must_be_smaller_than_chunk_size():
    with pytest.raises(ValueError):
        split_text("text", max_chars=100, overlap=100)


def test_prose_is_informative():
    assert is_informative("The total load is an estimate of the total electricity consumption.")


def test_chart_labels_are_not_informative():
    assert not is_informative("Hours MW 00 01 02 03 04 05 06 0 2000 4000 6000 8000 10 000")


def test_short_fragments_are_not_informative():
    assert not is_informative("menu Grid data")


def test_number_runs_are_removed():
    axis = "Elia grid load 00 01 02 03 04 05 0 2000 4000 6000 Legend"
    assert strip_number_runs(axis).split() == ["Elia", "grid", "load", "Legend"]


def test_short_number_groups_are_kept():
    text = "Between 2020 and 2022, MAPE fell from 3.75 to 3.22 percent."
    assert strip_number_runs(text) == text
