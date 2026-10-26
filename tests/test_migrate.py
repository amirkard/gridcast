"""Schema migration tests. The session fixture has already applied the schema once."""

import threading
from pathlib import Path

import pytest
from sqlalchemy import text

from gridcast import migrate
from gridcast.db import get_engine


def test_applies_every_file_in_name_order():
    names = migrate.apply(get_engine())
    assert names == sorted(names)
    assert names[0].startswith("001_")
    assert "008_documents.sql" in names


def test_is_idempotent():
    """The init container runs on every pod start, so a second run must change nothing."""
    engine = get_engine()
    with engine.connect() as conn:
        before = conn.execute(text("select count(*) from load_raw")).scalar_one()
    migrate.apply(engine)
    migrate.apply(engine)
    with engine.connect() as conn:
        after = conn.execute(text("select count(*) from load_raw")).scalar_one()
    assert after == before > 0


def test_concurrent_runs_do_not_fail():
    """Several pods can start together; the advisory lock serialises them."""
    engine = get_engine(pool_size=4)
    errors: list[Exception] = []

    def run():
        try:
            migrate.apply(engine)
        except Exception as e:  # collect, so that the test reports them
            errors.append(e)

    threads = [threading.Thread(target=run) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    engine.dispose()
    assert errors == []


def test_empty_sql_dir_is_an_error(tmp_path: Path):
    """A wrong working directory must fail loudly, not 'apply' nothing."""
    with pytest.raises(FileNotFoundError):
        migrate.sql_files(tmp_path)


def test_wait_for_database_returns_when_reachable():
    migrate.wait_for_database(get_engine(), timeout_s=5)
