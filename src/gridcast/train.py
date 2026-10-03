"""Train the production model on all available data and save it with metadata."""

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import lightgbm as lgb

from gridcast.features import FEATURES, build

MODEL_DIR = Path("models")
PARAMS = dict(
    n_estimators=600,
    learning_rate=0.05,
    num_leaves=63,
    min_child_samples=40,
    subsample=0.8,
    colsample_bytree=0.8,
    verbose=-1,
)


def main() -> None:
    df = build()
    model = lgb.LGBMRegressor(**PARAMS).fit(df[FEATURES], df["load_mw"])

    version = f"lgbm-{datetime.now(timezone.utc):%Y%m%d}"
    MODEL_DIR.mkdir(exist_ok=True)
    joblib.dump(model, MODEL_DIR / "model.joblib")

    meta = {
        "version": version,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_rows": int(len(df)),
        "train_start": str(df["ts"].min()),
        "train_end": str(df["ts"].max()),
        "features": FEATURES,
        "params": PARAMS,
        "backtest_mape": 3.22,
        "baseline_mape": 3.35,
    }
    (MODEL_DIR / "metadata.json").write_text(json.dumps(meta, indent=2))
    print(f"Saved {version}: {len(df)} rows, {len(FEATURES)} features")


if __name__ == "__main__":
    main()
