"""Experiment tracking with MLflow.

Backtests and training runs log their parameters, metrics, and files to
MLflow, so that every model can be traced to the run that produced it and the
evaluation that justified it. Tracking is optional: without MLflow installed
(it is in the "tracking" dependency group), or with GRIDCAST_TRACKING=off,
every function here does nothing.

The tracking store is MLFLOW_TRACKING_URI, or a local SQLite file
(mlflow.db) when it is not set. To look at the runs in the MLflow web UI, in
its own environment so that its dependencies do not mix with the project's:

    uvx mlflow ui --backend-store-uri sqlite:///mlflow.db
"""

import os
import subprocess
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

DEFAULT_URI = "sqlite:///mlflow.db"

_active = False


def enabled() -> bool:
    if os.environ.get("GRIDCAST_TRACKING", "on").lower() in ("off", "0", "false"):
        return False
    try:
        import mlflow  # noqa: F401
    except ImportError:
        return False
    return True


def git_commit() -> str:
    """The commit of the code that ran, or 'unknown' outside a repository."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


@contextmanager
def run(experiment: str, run_name: str, tags: Mapping[str, str] | None = None) -> Iterator[Any]:
    """Yield an active MLflow run, or None when tracking is off."""
    global _active
    if not enabled():
        print("experiment tracking is off (MLflow not installed, or GRIDCAST_TRACKING=off)")
        yield None
        return

    import mlflow

    if not os.environ.get("MLFLOW_TRACKING_URI"):
        mlflow.set_tracking_uri(DEFAULT_URI)
    mlflow.set_experiment(experiment)
    with mlflow.start_run(run_name=run_name) as active:
        mlflow.set_tags({"git_commit": git_commit(), **(tags or {})})
        _active = True
        try:
            yield active
        finally:
            _active = False


def log(
    params: Mapping[str, Any] | None = None,
    metrics: Mapping[str, float] | None = None,
    tags: Mapping[str, str] | None = None,
) -> None:
    if not _active:
        return
    import mlflow

    if params:
        mlflow.log_params(dict(params))
    if metrics:
        mlflow.log_metrics({k: float(v) for k, v in metrics.items()})
    if tags:
        mlflow.set_tags(dict(tags))


def log_series(name: str, values: Sequence[float]) -> None:
    """One metric per step, for example the error of each backtest fold."""
    if not _active:
        return
    import mlflow

    for step, value in enumerate(values):
        mlflow.log_metric(name, float(value), step=step)


def artifact(path: Path | str) -> None:
    if not _active:
        return
    import mlflow

    mlflow.log_artifact(str(path))
