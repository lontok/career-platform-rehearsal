from sqlalchemy import create_engine

from app.core.config import Settings, normalize_database_url


def test_postgresql_url_uses_psycopg_driver() -> None:
    assert (
        normalize_database_url("postgresql://user:secret@db.internal:5432/railway")
        == "postgresql+psycopg://user:secret@db.internal:5432/railway"
    )


def test_short_postgres_scheme_uses_psycopg_driver() -> None:
    assert (
        normalize_database_url("postgres://user:secret@host:5432/railway")
        == "postgresql+psycopg://user:secret@host:5432/railway"
    )


def test_query_string_survives_the_rewrite() -> None:
    assert (
        normalize_database_url("postgresql://u:p@host:5432/db?sslmode=require")
        == "postgresql+psycopg://u:p@host:5432/db?sslmode=require"
    )


def test_other_urls_pass_through_unchanged() -> None:
    for url in (
        "sqlite:///./data/resume.db",
        "sqlite+pysqlite:///:memory:",
        "postgresql+psycopg://u:p@host/db",
    ):
        assert normalize_database_url(url) == url


def test_settings_rewrites_database_url_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host:5432/db")

    assert Settings().database_url == "postgresql+psycopg://u:p@host:5432/db"


def test_engine_for_rewritten_url_uses_psycopg(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host:5432/db")

    engine = create_engine(Settings().database_url)

    assert engine.dialect.name == "postgresql"
    assert engine.dialect.driver == "psycopg"
