"""Load the test fixture into an empty database once per session."""

import csv
from pathlib import Path

import pytest
from sqlalchemy import text

from gridcast import migrate
from gridcast.db import get_engine

FIXTURES = Path("tests/fixtures")


def _already_loaded(conn) -> bool:
    try:
        n = conn.execute(text("select count(*) from load_raw")).scalar_one()
        return n > 0
    except Exception:  # table may not exist yet
        return False


@pytest.fixture(scope="session", autouse=True)
def database():
    engine = get_engine()

    # The same code path as the Kubernetes init container.
    migrate.apply(engine)

    with engine.connect() as conn:
        if _already_loaded(conn):
            return

    with engine.begin() as conn:
        for name, table, cols in (
            ("load_sample.csv", "load_raw", ["ts", "resolution", "load_mw", "forecast_da"]),
            ("weather_sample.csv", "weather_raw", ["ts", "temp_c"]),
        ):
            rows = list(csv.DictReader((FIXTURES / name).open()))
            for r in rows:
                for c in cols:
                    if r[c] == "":
                        r[c] = None
            placeholders = ", ".join(f":{c}" for c in cols)
            conn.execute(
                text(f"insert into {table} ({', '.join(cols)}) values ({placeholders}) "
                     f"on conflict (ts) do nothing"),
                rows,
            )
