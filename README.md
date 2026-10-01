# Gridcast

Electricity load forecasting service with an LLM agent interface.

**Live:** https://gridcast.fly.dev/docs

## Status
Week 1: FastAPI service, containerised, deployed to Fly.io.

## Run locally
```bash
uv sync
uv run uvicorn gridcast.main:app --reload
```

## Run in Docker
```bash
docker build -t gridcast .
docker run -p 8000:8000 gridcast
```
