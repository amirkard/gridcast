"""Walk-forward evaluation of day-ahead load forecasts."""

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from gridcast.features import FEATURES, build


def metrics(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    err = y - p
    return {
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(np.sqrt(np.mean(err**2))),
        "mape": float(np.mean(np.abs(err / y)) * 100),
    }


def seasonal_naive(tr: pd.DataFrame, te: pd.DataFrame) -> np.ndarray:
    """Last week, same time of day. The honest floor."""
    return te["lag_7d"].to_numpy()


def ridge(tr: pd.DataFrame, te: pd.DataFrame) -> np.ndarray:
    sc = StandardScaler().fit(tr[FEATURES])
    m = Ridge(alpha=1.0).fit(sc.transform(tr[FEATURES]), tr["load_mw"])
    return m.predict(sc.transform(te[FEATURES]))


def gbm(tr: pd.DataFrame, te: pd.DataFrame) -> np.ndarray:
    m = lgb.LGBMRegressor(
        n_estimators=600,
        learning_rate=0.05,
        num_leaves=63,
        min_child_samples=40,
        subsample=0.8,
        colsample_bytree=0.8,
        verbose=-1,
    ).fit(tr[FEATURES], tr["load_mw"])
    return m.predict(te[FEATURES])


MODELS = {"seasonal_naive": seasonal_naive, "ridge": ridge, "lightgbm": gbm}


def run(n_folds: int = 6, test_days: int = 30) -> pd.DataFrame:
    df = build()
    rows = []
    slots_per_day = 96
    test_size = test_days * slots_per_day

    for fold in range(n_folds):
        end = len(df) - fold * test_size
        start = end - test_size
        if start <= test_size:
            break
        tr, te = df.iloc[:start], df.iloc[start:end]

        for name, fn in MODELS.items():
            pred = fn(tr, te)
            mask = ~np.isnan(pred)
            r = metrics(te["load_mw"].to_numpy()[mask], pred[mask])
            r |= {"model": name, "fold": fold, "test_start": te["ts"].iloc[0]}
            rows.append(r)

        # the professional reference, on exactly the same rows
        r = metrics(te["load_mw"].to_numpy(), te["forecast_da"].to_numpy())
        r |= {"model": "elia_day_ahead", "fold": fold, "test_start": te["ts"].iloc[0]}
        rows.append(r)

    return pd.DataFrame(rows)

def compare(res: pd.DataFrame, a: str, b: str) -> None:
    """Paired comparison across folds — both models saw identical test rows."""
    pa = res[res.model == a].set_index("fold")["mape"]
    pb = res[res.model == b].set_index("fold")["mape"]
    d = (pa - pb).dropna()
    _, p = stats.ttest_rel(pa[d.index], pb[d.index])
    lo, hi = stats.t.interval(0.95, len(d) - 1, d.mean(), stats.sem(d))
    print(f"{a} - {b}: mean diff {d.mean():+.2f} pp, "
          f"95% CI [{lo:+.2f}, {hi:+.2f}], p={p:.3f}")

if __name__ == "__main__":
    # in backtest.py, change the default
    res = run(n_folds=24, test_days=14)
    summary = (
        res.groupby("model")[["mae", "rmse", "mape"]]
        .agg(["mean", "std"])
        .round(2)
        .sort_values(("mape", "mean"))
    )
    print(summary)
    res.to_csv("results/backtest.csv", index=False)
    compare(res, "lightgbm", "ridge")
    compare(res, "lightgbm", "elia_day_ahead")
