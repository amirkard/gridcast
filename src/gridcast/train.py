"""Train the production model on all available data and save it with metadata."""

import json
from datetime import UTC, datetime
from pathlib import Path

import joblib
import lightgbm as lgb

from gridcast import tracking
from gridcast.features import FEATURES, build

MODEL_DIR = Path("models")

# The one definition of the model's hyperparameters. backtest.py uses it too,
# so the model that was evaluated is the model that is deployed.
PARAMS = {
    "n_estimators": 600,
    "learning_rate": 0.05,
    "num_leaves": 63,
    "min_child_samples": 40,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "verbose": -1,
}


def main() -> None:
    version = f"lgbm-{datetime.now(UTC):%Y%m%d}"
    with tracking.run("gridcast-train", version) as active:
        df = build()
        model = lgb.LGBMRegressor(**PARAMS).fit(df[FEATURES], df["load_mw"])
        meta = metadata(df, version)
        # The model file names the run that made it, and the run holds the file.
        meta["mlflow_run_id"] = active.info.run_id if active else None

        MODEL_DIR.mkdir(exist_ok=True)
        joblib.dump(model, MODEL_DIR / "model.joblib")
        (MODEL_DIR / "metadata.json").write_text(json.dumps(meta, indent=2))

        ev = meta["evaluation"]
        tracking.log(
            params={**PARAMS, "n_features": len(FEATURES), "n_rows": len(df)},
            metrics={
                "backtest_mape_pct": ev["model_mape_pct"],
                "baseline_mape_pct": ev["baseline_mape_pct"],
                "paired_difference_pp": ev["paired_difference_pp"],
            },
            tags={
                "model_version": version,
                "train_start": meta["train_start"],
                "train_end": meta["train_end"],
            },
        )
        tracking.artifact(MODEL_DIR / "model.joblib")
        tracking.artifact(MODEL_DIR / "metadata.json")
    print(f"Saved {version}: {len(df)} rows, {len(FEATURES)} features")


def metadata(df, version: str) -> dict:
    return {
        "version": version,
        "trained_at": datetime.now(UTC).isoformat(),
        "n_rows": len(df),
        "resolution": "15 minutes",
        "train_start": str(df["ts"].min()),
        "train_end": str(df["ts"].max()),
        "features": FEATURES,
        "params": PARAMS,
        "evaluation": {
            "method": "walk-forward, 24 folds of 14 days, expanding window",
            "model_mape_pct": 3.22,
            "model_mape_sd": 0.95,
            "baseline": "Elia published day-ahead forecast",
            "baseline_mape_pct": 3.35,
            "baseline_mape_sd": 0.81,
            "paired_difference_pp": -0.13,
            "ci95_pp": [-0.49, 0.23],
            "p_value": 0.451,
            "conclusion": (
                "Statistically indistinguishable from the TSO forecast. "
                "The model does NOT outperform it: the 95% interval crosses zero."
            ),
            "caveat": (
                "Measured temperature was used, not forecast temperature. "
                "The TSO forecast relied on a weather forecast with its own "
                "error, so this comparison favours the model."
            ),
        },
    }


if __name__ == "__main__":
    main()
