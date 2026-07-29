from app.db.url import normalize_database_url


def test_normalize_render_postgresql_url() -> None:
    assert (
        normalize_database_url("postgresql://user:pass@host:5432/osint")
        == "postgresql+asyncpg://user:pass@host:5432/osint"
    )


def test_normalize_legacy_postgres_url() -> None:
    assert (
        normalize_database_url("postgres://user:pass@host:5432/osint")
        == "postgresql+asyncpg://user:pass@host:5432/osint"
    )


def test_keep_explicit_asyncpg_url() -> None:
    value = "postgresql+asyncpg://user:pass@host:5432/osint"
    assert normalize_database_url(value) == value
