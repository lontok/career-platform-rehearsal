"""Proof that the migrations and seed work on a real PostgreSQL database.

These tests run only when POSTGRES_TEST_URL is set. They drop every table in that
database, so point it at an empty Railway database, never one with real content.
The guard below refuses when any profile other than the fictional sample exists.
Teardown leaves the database empty and at Alembic head.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, Engine, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.core.config import normalize_database_url
from app.db.base import Base
from app.seed import seed_demo_content
from tests import seed_samples
from tests.test_migrations import _alembic_config

POSTGRES_TEST_URL = os.environ.get("POSTGRES_TEST_URL")
SAMPLE_NAME = seed_samples.SAMPLE_PROFILE["full_name"]


def refuse_real_profiles(connection: Connection) -> None:
    if not inspect(connection).has_table("profiles"):
        return
    names = connection.execute(text("SELECT full_name FROM profiles")).scalars().all()
    real = sorted({name for name in names if name != SAMPLE_NAME})
    if real:
        raise RuntimeError(
            "Refusing to drop tables in a database that holds real profiles: "
            + ", ".join(real)
        )


def _drop_everything(engine: Engine) -> None:
    with engine.begin() as connection:
        refuse_real_profiles(connection)
        Base.metadata.drop_all(connection)
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))


@pytest.fixture
def postgres_engine(monkeypatch) -> Iterator[Engine]:
    if not POSTGRES_TEST_URL:
        pytest.skip("Set POSTGRES_TEST_URL to run against a real PostgreSQL database.")
    monkeypatch.setenv("DATABASE_URL", POSTGRES_TEST_URL)
    engine = create_engine(normalize_database_url(POSTGRES_TEST_URL))
    _drop_everything(engine)
    try:
        yield engine
    finally:
        _drop_everything(engine)
        command.upgrade(_alembic_config(), "head")
        engine.dispose()


def _count(engine: Engine, table: str) -> int:
    with engine.connect() as connection:
        return connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()


def test_guard_refuses_a_database_with_real_profiles(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'guard.db'}")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO profiles (full_name, headline, summary, location,"
                " target_roles, email, published, seed_key)"
                " VALUES ('Greg Lontok', 'h', 's', 'l', '', '', 1, 'profile:primary')"
            )
        )

    with (
        engine.begin() as connection,
        pytest.raises(RuntimeError, match="Greg Lontok"),
    ):
        refuse_real_profiles(connection)


def test_guard_allows_only_the_sample_profile(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'guard.db'}")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO profiles (full_name, headline, summary, location,"
                " target_roles, email, published)"
                " VALUES (:name, 'h', 's', 'l', '', '', 1)"
            ),
            {"name": SAMPLE_NAME},
        )

    with engine.begin() as connection:
        refuse_real_profiles(connection)


def test_migration_02_keeps_one_published_profile(postgres_engine) -> None:
    config = _alembic_config()
    command.upgrade(config, "20260915_01")
    with postgres_engine.begin() as connection:
        for profile_id, email in (
            (1, "other@example.com"),
            (2, "alex.parker@example.com"),
        ):
            connection.execute(
                text(
                    "INSERT INTO profiles (id, full_name, headline, summary, location,"
                    " target_roles, email, published)"
                    " VALUES (:id, :name, 'Analyst', 'Summary.', 'Los Angeles', '',"
                    " :email, true)"
                ),
                {"id": profile_id, "name": SAMPLE_NAME, "email": email},
            )

    command.upgrade(config, "20260917_02")

    with postgres_engine.connect() as connection:
        published = (
            connection.execute(text("SELECT id FROM profiles WHERE published"))
            .scalars()
            .all()
        )
    assert published == [2]


def test_upgrade_seed_and_downgrade_keep_linked_rows(
    postgres_engine, sample_seed
) -> None:
    config = _alembic_config()
    command.upgrade(config, "head")
    seed_demo_content(session_factory=sessionmaker(bind=postgres_engine))

    accomplishments = _count(postgres_engine, "experience_accomplishments")
    links = _count(postgres_engine, "experience_skills")
    assert accomplishments > 0
    assert links > 0

    command.downgrade(config, "20260917_02")

    columns = [
        column["name"] for column in inspect(postgres_engine).get_columns("experiences")
    ]
    assert "featured" not in columns
    assert _count(postgres_engine, "experience_accomplishments") == accomplishments
    assert _count(postgres_engine, "experience_skills") == links

    command.upgrade(config, "head")


def test_only_one_profile_can_be_published(postgres_engine, sample_seed) -> None:
    command.upgrade(_alembic_config(), "head")
    seed_demo_content(session_factory=sessionmaker(bind=postgres_engine))
    insert = text(
        "INSERT INTO profiles (full_name, headline, summary, location,"
        " target_roles, email, published)"
        " VALUES (:name, 'h', 's', 'l', '', '', :published)"
    )

    with postgres_engine.begin() as connection:
        connection.execute(insert, {"name": SAMPLE_NAME, "published": False})

    with pytest.raises(IntegrityError), postgres_engine.begin() as connection:
        connection.execute(insert, {"name": SAMPLE_NAME, "published": True})
