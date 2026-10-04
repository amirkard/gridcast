"""Ingest population-weighted Belgian temperature from the Open-Meteo archive."""

import sys

import httpx
import pandas as pd
from sqlalchemy import text

from gridcast.db import get_engine

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"

# City, latitude, longitude, weight (roughly proportional to population served)
CITIES = [
    ("Brussels", 50.85, 4.35, 0.30),
    ("Antwerp", 51.22, 4.40, 0.25),
    ("Ghent", 51.05, 3.72, 0.15),
    ("Liege", 50.63, 5.57, 0.15),
    ("Charleroi", 50.41, 4.44, 0.15),
]


def _weighted_mean(blocks: list[dict]) -> pd.DataFrame:
    """Combine per-city hourly temperature into one population-weighted series."""
    if len(blocks) != len(CITIES):
        print(f"ERROR: expected {len(CITIES)} locations, got {len(blocks)}",
              file=sys.stderr)
        sys.exit(1)

    frames = []
    for (name, _, _, _), block in zip(CITIES, blocks, strict=True):
        h = block["hourly"]
        frames.append(
            pd.DataFrame({"ts": h["time"], name: h["temperature_2m"]}).set_index("ts")
        )
    wide = pd.concat(frames, axis=1)

    w = pd.Series({c[0]: c[3] for c in CITIES})
    weighted_sum = (wide.fillna(0) * w).sum(axis=1)
    weight_present = (wide.notna() * w).sum(axis=1)

    out = pd.DataFrame({
        "ts": pd.to_datetime(wide.index, utc=True),
        "temp_c": (weighted_sum / weight_present.replace(0, pd.NA)).to_numpy(),
    })
    print(f"  {len(out)} hourly rows, {out['temp_c'].isna().sum()} missing, "
          f"mean {out['temp_c'].mean():.1f} C")
    return out.dropna(subset=["temp_c"]).reset_index(drop=True)


def fetch(start: str, end: str) -> pd.DataFrame:
    """Historical archive for a date range."""
    params = {
        "latitude": ",".join(str(c[1]) for c in CITIES),
        "longitude": ",".join(str(c[2]) for c in CITIES),
        "start_date": start,
        "end_date": end,
        "hourly": "temperature_2m",
        "timezone": "UTC",
    }
    with httpx.Client(timeout=180) as client:
        r = client.get(ARCHIVE, params=params)
        r.raise_for_status()
        payload = r.json()
    return _weighted_mean(payload if isinstance(payload, list) else [payload])


def load(df: pd.DataFrame) -> int:
    engine = get_engine()
    sql = text("""
        insert into weather_raw (ts, temp_c)
        values (:ts, :temp_c)
        on conflict (ts) do update
          set temp_c = excluded.temp_c, ingested_at = now()
    """)
    rows = df.to_dict("records")
    with engine.begin() as conn:
        for i in range(0, len(rows), 5000):
            conn.execute(sql, rows[i : i + 5000])
    return len(rows)

FORECAST = "https://api.open-meteo.com/v1/forecast"


def fetch_forecast(days: int = 7) -> pd.DataFrame:
    """Hourly temperature forecast for the coming days (no key required)."""
    params = {
        "latitude": ",".join(str(c[1]) for c in CITIES),
        "longitude": ",".join(str(c[2]) for c in CITIES),
        "hourly": "temperature_2m",
        "forecast_days": days,
        "past_days": 2,
        "timezone": "UTC",
    }
    with httpx.Client(timeout=120) as client:
        r = client.get(FORECAST, params=params)
        r.raise_for_status()
        payload = r.json()
    return _weighted_mean(payload if isinstance(payload, list) else [payload])


def load_forecast(df: pd.DataFrame) -> int:
    engine = get_engine()
    sql = text("""
        insert into weather_forecast (ts, temp_c)
        values (:ts, :temp_c)
        on conflict (ts) do update
          set temp_c = excluded.temp_c, fetched_at = now()
    """)
    with engine.begin() as conn:
        conn.execute(sql, df.to_dict("records"))
    return len(df)

if __name__ == "__main__":
    start = sys.argv[1] if len(sys.argv) > 1 else "2022-12-01"
    end = sys.argv[2] if len(sys.argv) > 2 else "2026-10-02"
    print(f"{start} to {end}:")
    n = load(fetch(start, end))
    print(f"  {n} rows written")
