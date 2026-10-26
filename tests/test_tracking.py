"""Experiment tracking tests. They need MLflow (the "tracking" group, part of dev)."""

import pytest

from gridcast import tracking


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A throwaway MLflow store; the artifacts go under tmp_path too."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{tmp_path / 'mlflow.db'}")
    monkeypatch.delenv("GRIDCAST_TRACKING", raising=False)
    return tmp_path


def test_run_records_params_metrics_series_tags_and_files(store):
    mlflow = pytest.importorskip("mlflow")
    report = store / "backtest.csv"
    report.write_text("fold,mape\n0,3.1\n")

    with tracking.run("test-experiment", "run-1", tags={"purpose": "test"}) as active:
        tracking.log(params={"n_folds": 24}, metrics={"mape_mean": 3.22})
        tracking.log_series("lightgbm_mape", [3.1, 3.4, 3.0])
        tracking.artifact(report)
        run_id = active.info.run_id

    got = mlflow.get_run(run_id)
    assert got.data.params["n_folds"] == "24"
    assert got.data.metrics["mape_mean"] == pytest.approx(3.22)
    assert got.data.metrics["lightgbm_mape"] == pytest.approx(3.0)  # the last step
    assert got.data.tags["purpose"] == "test"
    assert "git_commit" in got.data.tags

    history = mlflow.tracking.MlflowClient().get_metric_history(run_id, "lightgbm_mape")
    assert [m.value for m in sorted(history, key=lambda m: m.step)] == [3.1, 3.4, 3.0]

    files = [f.path for f in mlflow.tracking.MlflowClient().list_artifacts(run_id)]
    assert files == ["backtest.csv"]


def test_off_switch_logs_nothing(store, monkeypatch):
    """Training must work without a tracking server: off means no run and no error."""
    monkeypatch.setenv("GRIDCAST_TRACKING", "off")
    with tracking.run("test-experiment", "run-2") as active:
        tracking.log(params={"a": 1}, metrics={"b": 2.0})
        tracking.log_series("c", [1.0])
        tracking.artifact(store / "does-not-exist.txt")
    assert active is None
    assert not (store / "mlflow.db").exists()


def test_helpers_do_nothing_outside_a_run(store):
    tracking.log(params={"a": 1})
    tracking.log_series("c", [1.0])
    tracking.artifact(store / "does-not-exist.txt")
