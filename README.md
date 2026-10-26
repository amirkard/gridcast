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

An LLM agent over the same data: four schema-defined tools (history query,
forecast, model provenance, document search) with a tool-calling loop and a turn limit.

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

## MCP server

The same tools are also exposed as a [Model Context
Protocol](https://modelcontextprotocol.io) server, so any MCP client (Claude
Code, Claude Desktop, an IDE) can query the grid data directly.

There is one tool contract, not two. `gridcast.mcp_server` serves the schemas
from `gridcast.tools.TOOLS` and dispatches to `gridcast.tools.DISPATCH`, the
same objects the in-house agent and the evaluation suite use. A test asserts
that the MCP listing and the agent's tool definitions are identical, so they
cannot drift apart.

Tool errors (an empty range, an invalid aggregate) reach the client with
`isError` set, not as ordinary data. The tests cover the in-memory protocol
path and a real stdio subprocess, as a desktop client would start it.

```bash
uv run python -m gridcast.mcp_server            # stdio transport
claude mcp add gridcast -- uv run --directory "$PWD" python -m gridcast.mcp_server
```

## Document search (RAG)

The agent can also answer questions about definitions and methods from a small
document library: grid-load definitions from ENTSO-E and Elia, plus this
README and the project notes. A fourth tool, `search_docs`, embeds the question
with a local model (bge-small-en-v1.5, 384 dimensions, no API key), finds the
closest chunks in PostgreSQL with pgvector, and returns them with their source,
title, page, and similarity score.

- **Chunking:** about 1,200 characters per chunk, ending at a paragraph,
  sentence, or word, with a 200-character overlap.
- **Noise filter:** runs of numbers (chart axes) are removed from PDF text,
  and chunks that are still mostly numbers or labels are skipped. A web page
  saved as PDF produced such chunks; they matched queries well and pushed the
  real definitions out of the top results.
- **Citations:** the agent must cite the source and page of each claim. If no
  passage answers the question, it must say so instead of answering from memory.
- **Untrusted text:** retrieved passages are quoted material, never
  instructions.
- **Evaluation:** five new cases cover an answer from the project notes, a
  definition with a citation, a question the documents do not cover, a
  question that needs both a document and the load data, and a prompt
  injection: `corpus/grid_load_glossary.md` contains a planted instruction to
  stop answering, and the agent must ignore it.

The documents themselves are not committed; `corpus/_sources.md` lists them.

## Deployment on Azure

Infrastructure as code with Bicep, in `infra/`:

- `database.bicep`: Azure Database for PostgreSQL (Flexible Server, version
  16) with pgvector allowed, and a firewall that admits one client address and
  Azure services.
- `app.bicep`: the API on Azure Container Apps, scaling to zero when idle. Its
  secrets (database URL, Anthropic API key, `/ask` token) live in Azure Key
  Vault; the app reads them through a managed identity that has only the
  "Key Vault Secrets User" role, so no secret value is stored in the app
  definition.

CI publishes the image to the GitHub Container Registry from master, but only
after lint, tests, and a smoke test that starts the image and waits for
`/health`. The smoke test exists because an image once built cleanly and then
could not start: LightGBM needs `libgomp1`, which the slim base image lacks.

The agent is reachable at `POST /ask` with an `X-Ask-Token` header, because
every call costs LLM tokens.

## Kubernetes

A Helm chart in `deploy/helm/gridcast` runs the same image on any Kubernetes
cluster:

- **API Deployment** with three probes. Liveness (`/livez`) never touches the
  database, so a database outage does not restart every pod; readiness
  (`/health`) does, so a pod that cannot reach the database gets no traffic.
- **Schema migration** as an init container (`python -m gridcast.migrate`).
  The SQL files are idempotent and run in one transaction under a PostgreSQL
  advisory lock, so several pods can start at the same time.
- **Daily data refresh** as a CronJob: this year's load from Elia, then the
  latest weather and the weather forecast.
- **Secrets** from an existing Secret in production (for example, filled from
  Azure Key Vault by the Secrets Store CSI driver). Only local clusters let the
  chart create one.
- **PostgreSQL with pgvector** in the cluster, for local use and CI only. Its
  generated password is kept on upgrade, because a new one would not match the
  data on the volume.
- **Non-root containers** without privilege escalation or Linux capabilities.

Try it on a local cluster with [kind](https://kind.sigs.k8s.io):

```bash
kind create cluster --name gridcast
docker build -t gridcast:local .
kind load docker-image gridcast:local --name gridcast
helm install gridcast deploy/helm/gridcast -f deploy/kind-values.yaml --wait
helm test gridcast
kubectl create job --from=cronjob/gridcast-ingest ingest-now   # load data now
kubectl port-forward svc/gridcast 8000:8000                    # http://localhost:8000/docs
```

To enable `POST /ask`, put the keys in a Secret and point the chart at it:

```bash
kubectl create secret generic gridcast-api \
  --from-literal=ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" --from-literal=ASK_TOKEN="$ASK_TOKEN"
helm upgrade gridcast deploy/helm/gridcast -f deploy/kind-values.yaml \
  --set secrets.existingSecret=gridcast-api --wait
```

CI installs the chart on a kind cluster on every push and runs `helm test`.

## Experiment tracking

Backtests and training runs log to MLflow (`gridcast.tracking`):

- **Backtest** (`python -m gridcast.backtest`): the fold setup, the model
  parameters, the mean and spread of each model's error, the error of every
  fold as a series, the paired comparisons with their confidence intervals,
  and `results/backtest.csv`.
- **Training** (`python -m gridcast.train`): the parameters, the data window,
  the evaluation numbers, the commit, and the model file with its metadata.
  `models/metadata.json` records the MLflow run ID, so a deployed model leads
  back to the run that made it.

Both use one definition of the LightGBM parameters (`train.PARAMS`), so the
model that was evaluated is the model that is deployed. Tracking is optional:
without MLflow, or with `GRIDCAST_TRACKING=off`, both scripts run as before.

```bash
uv run python -m gridcast.backtest
uvx mlflow ui --backend-store-uri sqlite:///mlflow.db   # http://localhost:5000
```

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

Python · PostgreSQL · pgvector · LightGBM · MLflow · FastAPI · Docker · Kubernetes · Helm ·
Azure (Container Apps, Key Vault, PostgreSQL, Bicep) · pytest · GitHub Actions ·
Anthropic API · MCP

## Run it

```bash
docker compose up -d
uv sync
uv run python -m gridcast.migrate
uv run python -m gridcast.ingest 2023 2024 2025 2026
uv run python -m gridcast.ingest_weather
uv run python -m gridcast.train
uv run python -m gridcast.ingest_docs   # documents in corpus/, see corpus/_sources.md
uv run uvicorn gridcast.main:app --reload

# Later, to bring the data up to date (current year, latest weather and forecast):
uv run python -m gridcast.ingest
uv run python -m gridcast.ingest_weather
```

```bash
uv run python -m gridcast.agent "What was the peak load in February 2026?"
uv run pytest tests/ -q          # tool contract tests, no API key needed
uv run python eval/run_eval.py   # agent evaluation, needs ANTHROPIC_API_KEY
```

CI runs lint, the tests against a real PostgreSQL service container, the
Docker build, a smoke test of the image, and the Helm chart on a kind cluster
on every push. The agent evaluation is run manually: it costs
money and is non-deterministic, so it does not belong on every commit.

## Known limitations

- Measured rather than forecast temperature in the backtest, as noted above.
- Scheduled ingest exists only on Kubernetes (the CronJob); the Azure
  deployment is refreshed by hand.
- Row-offset lags assume a complete 15-minute grid. `forecast_features` reads
  `load_raw`, which has one, so this holds in serving.
- The evaluation grader uses substring matching, which produces both false
  passes and false failures. New cases need manual reading for the first runs.
