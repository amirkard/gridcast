"""Ingest Belgian grid load from the Elia open data platform into PostgreSQL."""

import sys
from io import StringIO

import httpx
import pandas as pd
from sqlalchemy import text

from gridcast.db import get_engine

BASE = "https://opendata.elia.be/api/explore/v2.1/catalog/datasets/ods001"

# Candidate source columns, in order of preference, for each target column.
COLUMN_CANDIDATES = {
    "ts": ["datetime", "date_time", "timestamp"],
    "resolution": ["resolutioncode", "resolution_code", "resolution"],
    "load_mw": ["totalload", "total_load", "measured", "elia_grid_load"],
    "forecast_da": ["dayaheadforecast", "dayahead_forecast", "day_ahead_forecast"],
}


def fetch(start: str, end: str) -> pd.DataFrame:
    """Download one date range as CSV. Timestamps are requested in UTC."""
    params = {
        "where": f"datetime >= date'{start}' and datetime < date'{end}'",
        "delimiter": ",",
        "timezone": "UTC",
    }
    with httpx.Client(timeout=300, follow_redirects=True) as client:
        r = client.get(f"{BASE}/exports/csv", params=params)
        r.raise_for_status()
    return pd.read_csv(StringIO(r.text))


def pick(columns: list[str], candidates: list[str]) -> str | None:
    """Find the first candidate that matches a real column name."""
    norm = {c.lower().replace(" ", "").replace("_", ""): c for c in columns}
    for cand in candidates:
        key = cand.lower().replace("_", "")
        if key in norm:
            return norm[key]
    # fall back to a substring match
    for cand in candidates:
        key = cand.lower().replace("_", "")
        for n, original in norm.items():
            if key in n:
                return original
    return None


def transform(df: pd.DataFrame) -> pd.DataFrame:
    """Rename to the target schema, parse timestamps, drop unusable rows."""
    mapping: dict[str, str] = {}
    for target, candidates in COLUMN_CANDIDATES.items():
        source = pick(list(df.columns), candidates)
        if source is None and target in ("ts", "load_mw"):
            print(f"ERROR: no column found for '{target}'.", file=sys.stderr)
            print(f"Available columns: {list(df.columns)}", file=sys.stderr)
            sys.exit(1)
        if source is not None:
            mapping[source] = target
            print(f"  {target:<12} <- {source}")

    out = df[list(mapping)].rename(columns=mapping).copy()
    out["ts"] = pd.to_datetime(out["ts"], utc=True, format="mixed")

    for col in ("load_mw", "forecast_da"):
        if col not in out.columns:
            out[col] = None
        else:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    if "resolution" not in out.columns:
        out["resolution"] = None

    out = out[["ts", "resolution", "load_mw", "forecast_da"]]
    before = len(out)
    out = out.dropna(subset=["ts"]).drop_duplicates(subset=["ts"], keep="last")
    print(f"  {before} rows in, {len(out)} rows after cleaning")
    return out


def load(df: pd.DataFrame) -> int:
    engine = get_engine()
    sql = text(
        """
        insert into load_raw (ts, resolution, load_mw, forecast_da)
        values (:ts, :resolution, :load_mw, :forecast_da)
        on conflict (ts) do update
          set load_mw     = excluded.load_mw,
              forecast_da = excluded.forecast_da,
              resolution  = excluded.resolution,
              ingested_at = now()
        """
    )
    rows = df.astype(object).where(pd.notnull(df), None).to_dict("records")
    with engine.begin() as conn:
        for i in range(0, len(rows), 5000):
            conn.execute(sql, rows[i : i + 5000])
    return len(rows)


def ingest_year(year: int) -> None:
    print(f"\n{year}:")
    raw = fetch(f"{year}-01-01", f"{year + 1}-01-01")
    clean = transform(raw)
    n = load(clean)
    print(f"  {n} rows written")


if __name__ == "__main__":
    years = [int(a) for a in sys.argv[1:]] or [2024, 2025]
    for y in years:
        ingest_year(y)
