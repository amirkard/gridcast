"""Single source of the database URL and engine."""

import os

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine

load_dotenv()


def database_url() -> str:
    """Return DATABASE_URL with the psycopg 3 driver forced.

    Hosted providers hand out 'postgres://' or 'postgresql://', which SQLAlchemy
    maps to psycopg2. This project uses psycopg 3.
    """
    url = os.environ["DATABASE_URL"]
    for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://"):
        if url.startswith(prefix):
            return url
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def get_engine(**kwargs) -> Engine:
    return create_engine(database_url(), pool_pre_ping=True, **kwargs)
