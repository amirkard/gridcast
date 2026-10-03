"""Ingest population-weighted Belgian temperature from the Open-Meteo archive."""

import os
import sys

import httpx
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
DB = os.environ["DATABASE_URL"]
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"

# City, latitude, longitude, weight (roughly proportional to population served)
CITIES = [
    ("Brussels", 50.85, 4.35, 0.30),
    ("Antwerp", 51.22, 4.40, 0.25),
    ("Ghent", 51.05, 3.72, 0.15),
    ("Liege", 50.63, 5.57, 0.15),
    ("Charleroi", 50.41, 4.44, 0.15),
]


def fetch(start: str, end: str) -> pd.DataFrame:
    """One request for all cities. Returns a weighted national mean per hour."""
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

    # A multi-location request returns a list; a single location returns an object.
    blocks = payload if isinstance(payload, list) else [payload]
    if len(blocks) != len(CITIES):
        print(f"ERROR: expected {len(CITIES)} locations, got {len(blocks)}",
              file=sys.stderr)
        sys.exit(1)

    frames = []
    for (name, _, _, weight), block in zip(CITIES, blocks):
        h = block["hourly"]
        s = pd.DataFrame({"ts": h["time"], name: h["temperature_2m"]}).set_index("ts")
        frames.append(s * weight if False else s)

    wide = pd.concat(frames, axis=1)
    weights = {c[0]: c[3] for c in CITIES}
    total = sum(weights.values())

    # Weighted mean, ignoring any city with a missing reading for that hour.
    w = pd.Series(weights)
    present = wide.notna()
    weighted_sum = (wide.fillna(0) * w).sum(axis=1)
    weight_present = (present * w).sum(axis=1)
    out = pd.DataFrame({
        "ts": pd.to_datetime(wide.index, utc=True),
        "temp_c": (weighted_sum / weight_present.replace(0, pd.NA)).to_numpy(),
    })
    print(f"  {len(out)} hourly rows, {out['temp_c'].isna().sum()} missing, "
          f"mean {out['temp_c'].mean():.1f} C "
          f"(weights sum {total:.2f})")
    return out.dropna(subset=["temp_c"])


def load(df: pd.DataFrame) -> int:
    engine = create_engine(DB)
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


if __name__ == "__main__":
    start = sys.argv[1] if len(sys.argv) > 1 else "2022-12-01"
    end = sys.argv[2] if len(sys.argv) > 2 else "2026-10-02"
    print(f"{start} to {end}:")
    n = load(fetch(start, end))
    print(f"  {n} rows written")
