FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Use the image's Python 3.14; never download a different one.
ENV UV_PYTHON_DOWNLOADS=never

COPY pyproject.toml uv.lock README.md .python-version ./
COPY src/ ./src/

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

CMD ["uvicorn", "gridcast.main:app", "--host", "0.0.0.0", "--port", "8000"]
