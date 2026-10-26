"""Apply the SQL schema files in sql/ to the database, in name order.

Every file is idempotent ("create ... if not exists", "create or replace"), so
this is safe to run on each start. On Kubernetes it runs as an init container
before the API starts. Several pods can start at the same time, so the files are
applied in one transaction under an advisory lock: one pod applies them, and the
others wait and then find nothing to do.

    python -m gridcast.migrate
"""

import os
import sys
import time
from pathlib import Path

from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError

from gridcast.db import get_engine

SQL_DIR = Path(os.environ.get("GRIDCAST_SQL_DIR", "sql"))

# Any constant works; it only has to be the same for every caller.
LOCK_KEY = 4_812_001


def sql_files(sql_dir: Path = SQL_DIR) -> list[Path]:
    files = sorted(sql_dir.glob("*.sql"))
    if not files:
        raise FileNotFoundError(f"no .sql files in {sql_dir.resolve()}")
    return files


def wait_for_database(engine: Engine, timeout_s: float = 120, interval_s: float = 2) -> None:
    """Return when the database accepts connections; raise after timeout_s.

    On a new cluster the database pod can start after the API pod.
    """
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            with engine.connect() as conn:
                conn.execute(text("select 1"))
            return
        except OperationalError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(interval_s)


def apply(engine: Engine, sql_dir: Path = SQL_DIR) -> list[str]:
    """Apply every schema file in one transaction. Return the file names."""
    files = sql_files(sql_dir)
    with engine.begin() as conn:
        conn.execute(text("select pg_advisory_xact_lock(:key)"), {"key": LOCK_KEY})
        for path in files:
            conn.execute(text(path.read_text()))
    return [p.name for p in files]


def main() -> int:
    engine = get_engine()
    timeout_s = float(os.environ.get("GRIDCAST_DB_WAIT_SECONDS", "120"))
    wait_for_database(engine, timeout_s=timeout_s)
    applied = apply(engine)
    print(f"applied {len(applied)} schema files: {', '.join(applied)}")
    engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
