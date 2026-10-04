# Gridcast

[![CI](https://github.com/amirkard/gridcast/actions/workflows/ci.yml/badge.svg)](https://github.com/amirkard/gridcast/actions/workflows/ci.yml)

Day-ahead electricity load forecasting for the Belgian grid, with an API and an
LLM agent interface. Built to measure, not to demo: every claim below has a
baseline and a confidence interval behind it.

## Result

Day-ahead forecast of total Belgian grid load, 96 intervals per day.

| Model | MAPE (%) |
|---|---|
| **LightGBM (this project)** | **3.22 ± 0.95** |
| Elia published day-ahead forecast | 3.35 ± 0.81 |
| Ridge regression | 3.83 ± 1.13 |
| Seasonal naive | 5.17 ± 1.84 |

Statistically indistinguishable from the transmission system operator's own
published forecast: paired across 24 folds, −0.13 pp, 95% CI [−0.49, +0.23],
p = 0.45.

**This is not an outperformance claim.** The interval crosses zero. And the
comparison favours this model: it used measured temperature, while the TSO
forecast relied on a weather forecast carrying its own error.

## Approach

**Data.** 132k rows of 15-minute grid load from Elia open data, plus
population-weighted Belgian temperature from Open-Meteo. Stored as `timestamptz`
in UTC, so the two annual clock changes never collide on the primary key.

**Leakage constraint.** Measurements arrive about 2 h late and the furthest
target is 36 h ahead, so no feature may use data newer than 48 h. Every lag and
rolling window ends 192 intervals before its target. Shorter lags exist in the
training table and would improve validation scores, but are unavailable in
production.

**Validation.** Walk-forward, 24 folds of 14 days, expanding training window, no
shuffling. The TSO forecast is scored on identical rows. Results report mean and
fold standard deviation; model comparisons are paired t-tests with intervals.

**Weather.** Adding temperature, 24 h mean temperature and heating/cooling
degrees cut MAPE from 3.75 to 3.22 and closed a previously measured +0.40 pp
[0.03, 0.77] shortfall against the TSO.

## Agent

An LLM agent over the same data: three schema-defined tools (history query,
forecast, model provenance) with a tool-calling loop and a turn limit.

**Evaluation suite**, 22 cases covering lookups, comparisons, ambiguous phrasing,
out-of-range refusals, overclaim resistance and multi-step questions:

| Configuration | Pass rate |
|---|---|
| Full prompt and tool descriptions | 22/22, three consecutive runs |
| Degraded (no prompt, bare tool names) | 19/22 |

The degraded failures are the interesting part. Asked about load in **France**,
it queried the Belgian database and reported the result as French, with a
confident breakdown and no hedge — real data from one source presented as
another. It also chose averaging aggregations for questions about extremes,
understating a monthly minimum by 390 MW.

Read the 100% with care: the cases were iterated against this agent, and several
early failures were defects in the grader rather than the agent. The
full-versus-degraded gap is the defensible measurement.

## Findings worth reading

See [NOTES.md](NOTES.md). Two in particular:

**Tool completeness beats prompt wording.** An early version of the model-info
tool returned two accuracy numbers and no uncertainty. Asked how accurate the
model was, the agent answered that it "outperforms Belgium's official grid
operator forecast" — the exact claim the statistics rule out. The system prompt
already instructed it to report the confidence interval; it could not, so it
invented text. Fixing the tool contract fixed the behaviour. Rewording the
prompt would not have.

**Nulls are not all the same.** 730 rows had no measured load. 727 were future
timestamps inside the published forecast horizon, 3 were genuine dropouts. The
distinction decides whether you drop rows or redefine what "latest" means.

## Stack

Python · PostgreSQL · LightGBM · FastAPI · Docker · pytest · GitHub Actions ·
Anthropic API

## Run it

```bash
docker compose up -d
uv sync
uv run python -m gridcast.ingest 2023 2024 2025 2026
uv run python -m gridcast.ingest_weather
uv run python -m gridcast.train
uv run uvicorn gridcast.main:app --reload
```

```bash
uv run python -m gridcast.agent "What was the peak load in February 2026?"
uv run pytest tests/ -q          # tool contract tests, no API key needed
uv run python eval/run_eval.py   # agent evaluation, needs ANTHROPIC_API_KEY
```

CI runs lint, the tool tests against a real PostgreSQL service container, and
the Docker build on every push. The agent evaluation is run manually: it costs
money and is non-deterministic, so it does not belong on every commit.

## Known limitations

- Measured rather than forecast temperature in the backtest, as noted above.
- No scheduled ingest; data is refreshed by hand.
- Row-offset lags assume a complete 15-minute grid. `forecast_features` reads
  `load_raw`, which has one, so this holds in serving.
- The evaluation grader uses substring matching, which produces both false
  passes and false failures. New cases need manual reading for the first runs.
