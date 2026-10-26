FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Use the image's Python 3.14; never download a different one.
ENV UV_PYTHON_DOWNLOADS=never

COPY pyproject.toml uv.lock README.md .python-version ./
COPY src/ ./src/
COPY models/ ./models/
COPY sql/ ./sql/

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# Download the embedding model into the image, so that the first document
# search in a new container does not wait for a 130 MB download.
ENV FASTEMBED_CACHE_PATH=/app/.cache/fastembed
RUN python -c "from gridcast.embeddings import embed_query; embed_query('warm-up')"

# Run as an unprivileged user. The embedding cache stays writable for it,
# because the model library may write lock files next to the model.
RUN groupadd --gid 10001 gridcast \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin gridcast \
    && chown -R gridcast:gridcast /app/.cache
USER 10001:10001

EXPOSE 8000

CMD ["uvicorn", "gridcast.main:app", "--host", "0.0.0.0", "--port", "8000"]
