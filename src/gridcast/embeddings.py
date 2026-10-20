"""Text embeddings for retrieval.

A small local model (BAAI/bge-small-en-v1.5, 384 dimensions) through fastembed,
so retrieval needs no API key and costs nothing. The model downloads once, on
first use, and is cached afterwards.
"""

import os
from functools import cache

MODEL_NAME = "BAAI/bge-small-en-v1.5"
DIM = 384  # must match the vector(384) column in sql/008_documents.sql


@cache
def _model():
    from fastembed import TextEmbedding

    # The Docker image sets FASTEMBED_CACHE_PATH and downloads the model at build
    # time, so a container never waits for the download on its first query.
    return TextEmbedding(model_name=MODEL_NAME, cache_dir=os.environ.get("FASTEMBED_CACHE_PATH"))


def embed_passages(texts: list[str]) -> list[list[float]]:
    """Embed document chunks."""
    return [v.tolist() for v in _model().passage_embed(texts)]


def embed_query(query: str) -> list[float]:
    """Embed a search query. bge models use a query prefix; fastembed adds it."""
    return next(iter(_model().query_embed(query))).tolist()
