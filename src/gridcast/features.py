"""Build the model matrix from the SQL feature view."""

import os

import holidays
import numpy as np
import pandas as pd
from sqlalchemy import create_engine
from gridcast.db import get_engine


BE_HOLIDAYS = holidays.Belgium(years=range(2022, 2028))



def add_calendar(df: pd.DataFrame) -> pd.DataFrame:
    """Add calendar features. Used by both training and serving."""
    df = df.copy()
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    local = df["ts"].dt.tz_convert("Europe/Brussels")

    df["hour"] = local.dt.hour + local.dt.minute / 60.0
    df["dow"] = local.dt.dayofweek
    df["month"] = local.dt.month
    df["doy"] = local.dt.dayofyear
    df["is_weekend"] = (df["dow"] >= 5).astype(int)
    df["is_holiday"] = local.dt.date.map(lambda d: d in BE_HOLIDAYS).astype(int)
    df["is_working_day"] = (
        (df["is_weekend"] == 0) & (df["is_holiday"] == 0)
    ).astype(int)

    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    df["doy_sin"] = np.sin(2 * np.pi * df["doy"] / 365.25)
    df["doy_cos"] = np.cos(2 * np.pi * df["doy"] / 365.25)
    return df


def build() -> pd.DataFrame:
    engine = get_engine()
    df = pd.read_sql("select * from load_features order by ts", engine)
    df = add_calendar(df)
    return df.dropna(
        subset=["lag_14d", "roll_std_14d", "load_mw", "temp_c"]
    ).reset_index(drop=True)


FEATURES = [
    "lag_2d", "lag_3d", "lag_7d", "lag_14d",
    "roll_mean_14d", "roll_std_14d",
    "temp_c", "temp_24h_mean", "hdd", "cdd",
    "hour_sin", "hour_cos", "doy_sin", "doy_cos",
    "dow", "month", "is_weekend", "is_holiday", "is_working_day",
]

if __name__ == "__main__":
    d = build()
    print(d.shape)
    print(d[["ts", "load_mw", "lag_2d", "lag_7d", "is_holiday"]].head())
