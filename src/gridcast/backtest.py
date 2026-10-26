"""Walk-forward evaluation of day-ahead load forecasts."""

from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from gridcast import tracking
from gridcast.features import FEATURES, build
from gridcast.train import PARAMS


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
    m = lgb.LGBMRegressor(**PARAMS).fit(tr[FEATURES], tr["load_mw"])
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

def compare(res: pd.DataFrame, a: str, b: str) -> dict[str, float]:
    """Paired comparison across folds: both models saw identical test rows."""
    pa = res[res.model == a].set_index("fold")["mape"]
    pb = res[res.model == b].set_index("fold")["mape"]
    d = (pa - pb).dropna()
    _, p = stats.ttest_rel(pa[d.index], pb[d.index])
    lo, hi = stats.t.interval(0.95, len(d) - 1, d.mean(), stats.sem(d))
    print(f"{a} - {b}: mean diff {d.mean():+.2f} pp, "
          f"95% CI [{lo:+.2f}, {hi:+.2f}], p={p:.3f}")
    return {"diff_pp": float(d.mean()), "ci95_low_pp": float(lo),
            "ci95_high_pp": float(hi), "p_value": float(p)}


def main(n_folds: int = 24, test_days: int = 14) -> None:
    with tracking.run("gridcast-backtest", f"walk-forward-{n_folds}x{test_days}d"):
        res = run(n_folds=n_folds, test_days=test_days)
        summary = (
            res.groupby("model")[["mae", "rmse", "mape"]]
            .agg(["mean", "std"])
            .round(2)
            .sort_values(("mape", "mean"))
        )
        print(summary)
        out = Path("results/backtest.csv")
        out.parent.mkdir(exist_ok=True)
        res.to_csv(out, index=False)

        tracking.log(params={
            "n_folds": int(res["fold"].nunique()),
            "test_days": test_days,
            "features": len(FEATURES),
            **{f"lgbm_{k}": v for k, v in PARAMS.items()},
        })
        for model, g in res.sort_values("fold").groupby("model"):
            tracking.log(metrics={
                f"{model}_mape_mean": g["mape"].mean(),
                f"{model}_mape_std": g["mape"].std(),
                f"{model}_mae_mean": g["mae"].mean(),
            })
            tracking.log_series(f"{model}_mape_by_fold", g["mape"].tolist())
        for other in ("ridge", "elia_day_ahead"):
            c = compare(res, "lightgbm", other)
            tracking.log(metrics={f"lightgbm_vs_{other}_{k}": v for k, v in c.items()})
        tracking.artifact(out)


if __name__ == "__main__":
    main()
