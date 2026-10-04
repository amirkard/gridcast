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

## Evaluation

22 cases: lookups, comparisons, ambiguous phrasing, out-of-range refusals,
overclaim resistance, multi-tool questions.

| Configuration | Pass rate |
|---|---|
| Full prompt and tool descriptions | 22/22, three consecutive runs |
| Degraded (no prompt, bare tool names) | 19/22 |

The degraded run's failures are instructive: asked about **France**, it queried the
Belgian database and reported the result as French, without hedging. It also chose
averaging aggregations for questions about extremes, understating a monthly minimum
by 390 MW.

The absolute 100% should be read with care - the cases were iterated against this
agent, and several early failures were grader defects rather than agent defects.
The full-vs-degraded gap is the defensible measurement.
