from __future__ import annotations


def normalize_database_url(value: str) -> str:
    """Return a SQLAlchemy asyncpg URL for supported PostgreSQL inputs.

    Managed providers such as Render expose ``postgresql://`` connection strings,
    while SQLAlchemy's async engine requires an explicit async driver.
    """

    url = value.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url.removeprefix("postgresql://")
    return url
