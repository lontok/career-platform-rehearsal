# Railway and PostgreSQL migration implementation plan

> For agentic workers: REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking.

Goal: Move greglontok.com from the Azure test VM to Railway, with its rows copied into Railway PostgreSQL and checked against the source before DNS moves.

Architecture: The app stays one FastAPI service. Settings rewrites a plain PostgreSQL URL to the psycopg driver, and two dialect fixes make the four Alembic migrations run on PostgreSQL. A railway.json runs migrations before each deploy and never the seed. A small module copies and compares rows between any two databases through SQLAlchemy, and thin shell wrappers under deploy/scripts call it. Tasks 1 to 6 are code on a branch. Tasks 7 to 10 are the Railway, data, and Cloudflare steps, run in order with a check after each.

Tech stack: Python 3.12, uv with uv.lock, FastAPI, SQLAlchemy 2, Alembic, psycopg 3, pytest, Railway with Railpack, Cloudflare DNS.

Spec: docs/superpowers/specs/2026-10-07-railway-postgres-migration-design.md

## Global constraints

- Python 3.12 or later. Dependencies come from uv.lock, and every install is `uv sync --locked`.
- Local runs and pytest stay on SQLite. `uv run pytest -q` passes with no PostgreSQL available.
- Railway's pre-deploy command is exactly `alembic upgrade head`. No deploy runs the seed.
- No Dockerfile and no requirements.txt in the repo. Either one changes how Railpack builds.
- Cloudflare change is exactly four records. The root and www A records each become a CNAME to Railway's value for that name, set to DNS only, and Railway's two TXT records are added. Nothing else in Cloudflare changes, including TTLs, proxy, SSL mode, and redirects. Neither name redirects to the other.
- The test VM vm-career-platform-test-01 and resource group RG-CAREER-PLATFORM-TEST-01 stay. Nothing deallocates or deletes them.
- The lontok.xyz VM, vm-career-platform, is not touched.
- Commit messages carry no Claude attribution lines.
- Prose in README.md, PRODUCT.md, and comments follows Greg's voice rules: no em dashes, no semicolons, sentence-case headings, straight quotes.
- `uv run ruff format --check .` and `uv run ruff check .` pass after every task.
- Never print a database URL. Railway URLs carry the password.

## Deviations from the spec

These are small and deliberate. Each is repeated in the task it affects.

1. The spec's start command "runs Uvicorn through uv." Railpack's runtime image puts `/app/.venv/bin` on PATH and may not include uv, so the start and pre-deploy commands call `uvicorn` and `alembic` straight from that environment.
2. The spec puts two scripts under deploy/scripts. The logic lives in `app/db/transfer.py` so tests can import it, and `deploy/scripts/transfer-rows.sh` and `deploy/scripts/compare-rows.sh` are thin wrappers.
3. The spec says four raw UPDATE statements in migration 02 compare published to 0 and 1. Only one statement does, with three comparisons. That one is rewritten.
4. The spec's proof test "downgrades one step." It downgrades to 20260917_02, the same target the SQLite migration test uses, since that is where the featured column and the cascade risk live.
5. The spec's cutover step 4 drops the proof test's tables by hand. The test's teardown does it instead and leaves the database empty at head.

## Review focus

1. Running the seed against Railway before app/seed.py carries the edited row would quietly revert that row. The README says so in the content-update section, and Task 6 tests for that sentence.
2. Pointing the PostgreSQL proof test at a database that holds real rows must refuse before dropping anything. Task 4 tests the guard on SQLite so it runs in every pytest run.
3. Railway, Heroku-style, and query-string URLs: `postgres://` and `postgresql://...?sslmode=require` must both reach psycopg with the query intact. Task 1 tests both.
4. A copy from an old backup that is behind head, or a copy into the same database twice, must refuse with a message that names the revisions or the occupied tables and writes nothing. Task 3 tests both.
5. A stray requirements.txt or Dockerfile would make Railpack skip uv.lock. Task 5 tests that neither exists.

One more risk has no test because it lives in DNS. If only one of the two names moves, visitors see Railway's rows on one and the VM's rows on the other, and the copies drift after the first content update. Task 10 changes both names in the same sitting and checks both before it's done.

---

## File structure

- Modify `pyproject.toml` and `uv.lock`: add `psycopg[binary]`.
- Modify `app/core/config.py`: add `normalize_database_url` and apply it in Settings.
- Modify `app/models/profile.py`: add a `postgresql_where` clause to the single-published index.
- Modify `alembic/versions/20260917_02_add_seed_keys.py`: bound booleans in the one UPDATE, and the `postgresql_where` clause on the index.
- Create `app/db/transfer.py`: copy rows, compare rows, and the command line for both.
- Create `deploy/scripts/transfer-rows.sh` and `deploy/scripts/compare-rows.sh`: wrappers run from the repo root.
- Create `railway.json`: build and deploy settings as code.
- Create `tests/test_config.py`, `tests/test_transfer.py`, `tests/test_postgres.py`, and `tests/test_railway_config.py`.
- Modify `tests/test_models.py`, `tests/test_migrations.py`, and `tests/test_deploy_assets.py`.
- Modify `README.md`, `.env.example`, and `PRODUCT.md`.

## Before Task 1

- [ ] Create the branch.

```bash
git switch -c feat/railway-postgres
```

---

### Task 1: PostgreSQL driver and URL rewrite

Files:

- Modify: `pyproject.toml`, `uv.lock`
- Modify: `app/core/config.py`
- Create: `tests/test_config.py`

Interfaces:

- Consumes: nothing.
- Produces: `app.core.config.normalize_database_url(url: str) -> str`. `Settings().database_url` is already rewritten. Tasks 3 and 4 call `normalize_database_url` on URLs that don't come through Settings.

- [ ] Step 1: Write the failing tests in `tests/test_config.py`.

```python
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
```

- [ ] Step 2: Run the tests and confirm they fail.

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ImportError: cannot import name 'normalize_database_url'`.

- [ ] Step 3: Add the driver.

```bash
uv add "psycopg[binary]"
```

Expected: `pyproject.toml` lists `psycopg[binary]` under dependencies and `uv.lock` changes. The binary extra matters because Railway's image has no libpq.

- [ ] Step 4: Replace `app/core/config.py` with:

```python
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Railway hands out postgresql:// URLs. SQLAlchemy would pick the older psycopg2
# driver for that scheme, so point it at psycopg 3, which this project installs.
POSTGRES_SCHEMES = ("postgresql://", "postgres://")
PSYCOPG_SCHEME = "postgresql+psycopg://"


def normalize_database_url(url: str) -> str:
    for scheme in POSTGRES_SCHEMES:
        if url.startswith(scheme):
            return PSYCOPG_SCHEME + url[len(scheme) :]
    return url


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/resume.db"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url")
    @classmethod
    def _use_psycopg_driver(cls, value: str) -> str:
        return normalize_database_url(value)
```

- [ ] Step 5: Run the new tests and the full suite.

Run: `uv run pytest tests/test_config.py -v && uv run pytest -q`
Expected: 6 new tests pass, and the full suite passes with no failures.

- [ ] Step 6: Lint and commit.

```bash
uv run ruff format . && uv run ruff check .
git add pyproject.toml uv.lock app/core/config.py tests/test_config.py
git commit -m "feat: route PostgreSQL URLs to the psycopg driver"
```

---

### Task 2: Make the schema and migration 02 work on PostgreSQL

Files:

- Modify: `app/models/profile.py`
- Modify: `alembic/versions/20260917_02_add_seed_keys.py`
- Modify: `tests/test_models.py`
- Modify: `tests/test_migrations.py`

Interfaces:

- Consumes: `normalize_database_url` from Task 1, through Settings in `alembic/env.py`.
- Produces: an index named `ux_profiles_single_published` that is partial on both SQLite and PostgreSQL. Migration 02 runs on PostgreSQL.

This task fixes the one UPDATE in migration 02 that compares the boolean published column to 0 and 1. The spec counted four. There is one, with three comparisons.

- [ ] Step 1: Add the failing model test to the end of `tests/test_models.py`.

```python
def test_single_published_profile_index_is_partial_on_both_databases() -> None:
    from sqlalchemy.dialects import postgresql, sqlite
    from sqlalchemy.schema import CreateIndex

    index = next(
        index
        for index in Profile.__table__.indexes
        if index.name == "ux_profiles_single_published"
    )

    sqlite_ddl = str(CreateIndex(index).compile(dialect=sqlite.dialect()))
    postgres_ddl = str(CreateIndex(index).compile(dialect=postgresql.dialect()))

    assert "WHERE published = 1" in sqlite_ddl
    assert "WHERE published = true" in postgres_ddl
```

- [ ] Step 2: Add two failing migration tests to the end of `tests/test_migrations.py`. Add `import io` to its imports.

```python
def test_migration_02_keeps_one_published_profile_on_sqlite(
    monkeypatch, tmp_path
) -> None:
    database = tmp_path / "profiles.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database}")
    config = _alembic_config()
    command.upgrade(config, "20260915_01")

    with sqlite3.connect(database) as connection:
        for profile_id, email in ((1, "other@example.com"), (2, "alex.parker@example.com")):
            connection.execute(
                "INSERT INTO profiles (id, full_name, headline, summary, location,"
                " target_roles, email, published)"
                " VALUES (?, 'Alex Parker', 'Analyst', 'Summary.', 'Los Angeles',"
                " '', ?, 1)",
                (profile_id, email),
            )

    command.upgrade(config, "20260917_02")

    with sqlite3.connect(database) as connection:
        published = connection.execute(
            "SELECT id FROM profiles WHERE published = 1"
        ).fetchall()

    assert published == [(2,)]


def test_migrations_render_postgresql_booleans(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@localhost:5432/db")
    output = io.StringIO()
    config = Config(str(REPO_ROOT / "alembic.ini"), output_buffer=output)
    config.set_main_option("script_location", str(REPO_ROOT / "alembic"))

    command.upgrade(config, "head", sql=True)

    sql = " ".join(output.getvalue().split())
    assert "published = 1" not in sql
    assert "SET published = false WHERE published = true" in sql
    assert "WHERE published = true" in sql
```

The second test renders the migrations as PostgreSQL SQL without a server. Alembic's offline mode needs only the dialect, which Task 1's driver provides.

- [ ] Step 3: Run the new tests and confirm they fail.

Run: `uv run pytest tests/test_models.py::test_single_published_profile_index_is_partial_on_both_databases tests/test_migrations.py -v`
Expected: the index test FAILS because the PostgreSQL DDL has no WHERE clause. The render test FAILS on `"published = 1" not in sql`. The SQLite profile test PASSES already. It pins today's behavior so the rewrite can't change it.

- [ ] Step 4: Change the index in `app/models/profile.py`.

```python
        Index(
            "ux_profiles_single_published",
            "published",
            unique=True,
            sqlite_where=text("published = 1"),
            postgresql_where=text("published = true"),
        ),
```

- [ ] Step 5: In `alembic/versions/20260917_02_add_seed_keys.py`, replace the `UPDATE profiles SET published = 0 ...` statement with:

```python
    # Bound booleans render as 1 and 0 on SQLite and true and false on PostgreSQL,
    # which rejects a boolean column compared to an integer.
    op.execute(
        sa.text(
            """
            UPDATE profiles
            SET published = :unpublished
            WHERE published = :published
              AND id != (
                  SELECT id
                  FROM profiles
                  WHERE published = :published
                  ORDER BY
                      CASE WHEN seed_key = 'profile:primary' THEN 0 ELSE 1 END,
                      id
                  LIMIT 1
              )
            """
        ).bindparams(
            sa.bindparam("unpublished", False, type_=sa.Boolean()),
            sa.bindparam("published", True, type_=sa.Boolean()),
        )
    )
```

Then change the index in the same file:

```python
    op.create_index(
        "ux_profiles_single_published",
        "profiles",
        ["published"],
        unique=True,
        sqlite_where=sa.text("published = 1"),
        postgresql_where=sa.text("published = true"),
    )
```

Leave migrations 01, 03, and 04 alone. Their string and date comparisons are valid on PostgreSQL.

- [ ] Step 6: Run the tests and the full suite.

Run: `uv run pytest tests/test_models.py tests/test_migrations.py -v && uv run pytest -q`
Expected: all pass, including the existing `test_upgrade_keeps_experience_children`.

- [ ] Step 7: Check the real local database still migrates cleanly.

Run: `uv run alembic upgrade head && uv run alembic current`
Expected: `20261006_04 (head)` and no error. Migration 02 already ran on this file, so nothing reruns.

- [ ] Step 8: Lint and commit.

```bash
uv run ruff format . && uv run ruff check .
git add app/models/profile.py alembic/versions/20260917_02_add_seed_keys.py tests/test_models.py tests/test_migrations.py
git commit -m "fix: make the profile index and migration 02 valid on PostgreSQL"
```

---

### Task 3: Copy and compare rows between databases

Files:

- Create: `app/db/transfer.py`
- Create: `deploy/scripts/transfer-rows.sh`
- Create: `deploy/scripts/compare-rows.sh`
- Create: `tests/test_transfer.py`

Interfaces:

- Consumes: `normalize_database_url` from Task 1. `Base.metadata` with every model registered through `app.models`.
- Produces, in `app.db.transfer`:
  - `CONTENT_TABLES: tuple[str, ...]`, parents before children.
  - `class TransferRefused(RuntimeError)`.
  - `copy_rows(source_url: str, target_url: str) -> dict[str, int]`, rows copied per table.
  - `compare_databases(source_url: str, target_url: str) -> Comparison`, where `Comparison` has `counts: dict[str, tuple[int, int]]`, `differences: list[str]`, and a `matches: bool` property.
  - `main(argv: list[str] | None = None) -> int`, the command line. Exit 0 on success or a match, 1 on a refusal or a difference, and 64 on bad usage.
- Task 9 runs the two wrappers.

The spec puts both scripts under deploy/scripts. The logic lives in `app/db/transfer.py` so tests import it directly, and the two wrappers there call it.

- [ ] Step 1: Write the failing tests in `tests/test_transfer.py`.

```python
from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.transfer import (
    CONTENT_TABLES,
    TransferRefused,
    compare_databases,
    copy_rows,
    main,
)
from app.seed import seed_demo_content
from tests.test_migrations import _alembic_config


def _migrated(monkeypatch, path: Path, revision: str = "head") -> str:
    url = f"sqlite:///{path}"
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(_alembic_config(), revision)
    return url


@pytest.fixture
def source_url(monkeypatch, tmp_path, sample_seed) -> str:
    url = _migrated(monkeypatch, tmp_path / "source.db")
    engine = create_engine(url)
    seed_demo_content(session_factory=sessionmaker(bind=engine))
    engine.dispose()
    return url


@pytest.fixture
def target_url(monkeypatch, tmp_path) -> str:
    return _migrated(monkeypatch, tmp_path / "target.db")


def _count(url: str, table: str) -> int:
    with sqlite3.connect(url.removeprefix("sqlite:///")) as connection:
        return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_copy_reproduces_every_row(source_url, target_url) -> None:
    copied = copy_rows(source_url, target_url)

    assert list(copied) == list(CONTENT_TABLES)
    assert all(copied[table] > 0 for table in CONTENT_TABLES)
    comparison = compare_databases(source_url, target_url)
    assert comparison.matches, comparison.differences
    assert all(source == target for source, target in comparison.counts.values())


def test_copy_refuses_a_target_that_already_has_rows(source_url, target_url) -> None:
    copy_rows(source_url, target_url)
    before = {table: _count(target_url, table) for table in CONTENT_TABLES}

    with pytest.raises(TransferRefused, match="already has rows in: profiles"):
        copy_rows(source_url, target_url)

    assert {table: _count(target_url, table) for table in CONTENT_TABLES} == before


def test_copy_refuses_a_target_behind_head(monkeypatch, tmp_path, source_url) -> None:
    behind = _migrated(monkeypatch, tmp_path / "behind.db", "20261006_03")

    with pytest.raises(TransferRefused, match="target is at 20261006_03"):
        copy_rows(source_url, behind)

    assert _count(behind, "profiles") == 0


def test_copy_refuses_an_unmigrated_target(tmp_path, source_url) -> None:
    empty = f"sqlite:///{tmp_path / 'empty.db'}"

    with pytest.raises(TransferRefused, match="target is at None"):
        copy_rows(source_url, empty)


def test_compare_reports_a_changed_cell(source_url, target_url) -> None:
    copy_rows(source_url, target_url)
    with sqlite3.connect(target_url.removeprefix("sqlite:///")) as connection:
        connection.execute("UPDATE experiences SET summary = 'Edited.' WHERE id = 1")

    comparison = compare_databases(source_url, target_url)

    assert not comparison.matches
    assert len(comparison.differences) == 1
    assert comparison.differences[0].startswith("experiences id=1: summary differs")
    assert "'Edited.'" in comparison.differences[0]


def test_compare_reports_a_missing_row(source_url, target_url) -> None:
    copy_rows(source_url, target_url)
    with sqlite3.connect(target_url.removeprefix("sqlite:///")) as connection:
        connection.execute("DELETE FROM education WHERE id = 1")

    comparison = compare_databases(source_url, target_url)

    assert comparison.differences == ["education id=1: missing from target"]
    assert comparison.counts["education"] == (1, 0)


def test_command_line_exit_codes_and_no_urls_in_output(
    source_url, target_url, capsys
) -> None:
    assert main(["compare", source_url, target_url]) == 1
    assert main(["copy", source_url, target_url]) == 0
    assert main(["compare", source_url, target_url]) == 0
    assert main(["copy", source_url, target_url]) == 1
    assert main(["bogus"]) == 64

    captured = capsys.readouterr()
    assert "sqlite:///" not in captured.out + captured.err
    assert "Match." in captured.out


def test_wrappers_reject_missing_arguments() -> None:
    for script in ("deploy/scripts/transfer-rows.sh", "deploy/scripts/compare-rows.sh"):
        result = subprocess.run(
            ["bash", script], check=False, capture_output=True, text=True
        )
        assert result.returncode == 64
        assert "Usage:" in result.stderr
```

The sample seed fills every content table, including accomplishments and both skill link tables, so the copy test covers the foreign-key order.

- [ ] Step 2: Run the tests and confirm they fail.

Run: `uv run pytest tests/test_transfer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.db.transfer'`.

- [ ] Step 3: Create `app/db/transfer.py`.

```python
"""Copy resume rows from one database to another, and compare the two.

Run from the repo root:

    uv run python -m app.db.transfer copy SOURCE_URL TARGET_URL
    uv run python -m app.db.transfer compare SOURCE_URL TARGET_URL

Output never includes either URL, since a Railway URL carries the password.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine, create_engine, func, select, text
from sqlalchemy.exc import SQLAlchemyError

from app import models  # noqa: F401  registers every table on Base.metadata
from app.core.config import normalize_database_url
from app.db.base import Base

REPO_ROOT = Path(__file__).resolve().parents[2]

# Parents come before children, so every foreign key points at a row already copied.
CONTENT_TABLES = (
    "profiles",
    "skills",
    "experiences",
    "experience_accomplishments",
    "experience_skills",
    "projects",
    "project_skills",
    "education",
)

# Tables with an integer id. On PostgreSQL their id sequences must move past the
# copied ids, or the next insert collides with a copied row.
SEQUENCE_TABLES = (
    "profiles",
    "skills",
    "experiences",
    "experience_accomplishments",
    "projects",
    "education",
)


class TransferRefused(RuntimeError):
    """Raised when a copy would be unsafe. Nothing was written."""


@dataclass(frozen=True)
class Comparison:
    counts: dict[str, tuple[int, int]]
    differences: list[str]

    @property
    def matches(self) -> bool:
        return not self.differences


def _engine(url: str) -> Engine:
    return create_engine(normalize_database_url(url))


def _expected_head() -> str:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    return ScriptDirectory.from_config(config).get_current_head()


def _revision(engine: Engine) -> str | None:
    try:
        with engine.connect() as connection:
            return connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one_or_none()
    except SQLAlchemyError:
        return None


def _rows(connection: Connection, name: str) -> list[dict]:
    table = Base.metadata.tables[name]
    statement = select(table).order_by(*table.primary_key.columns)
    return [dict(row) for row in connection.execute(statement).mappings()]


def _key_label(table_name: str, row: dict) -> str:
    table = Base.metadata.tables[table_name]
    return ", ".join(f"{column.name}={row[column.name]}" for column in table.primary_key.columns)


def copy_rows(source_url: str, target_url: str) -> dict[str, int]:
    source = _engine(source_url)
    target = _engine(target_url)
    try:
        head = _expected_head()
        source_revision = _revision(source)
        target_revision = _revision(target)
        if source_revision != head or target_revision != head:
            raise TransferRefused(
                f"Both databases must be at Alembic head {head}. "
                f"The source is at {source_revision}, "
                f"and the target is at {target_revision}."
            )

        with source.connect() as source_connection:
            rows = {name: _rows(source_connection, name) for name in CONTENT_TABLES}

        copied: dict[str, int] = {}
        with target.begin() as target_connection:
            occupied = [
                name
                for name in CONTENT_TABLES
                if target_connection.execute(
                    select(func.count()).select_from(Base.metadata.tables[name])
                ).scalar_one()
            ]
            if occupied:
                raise TransferRefused(
                    "The target already has rows in: "
                    + ", ".join(occupied)
                    + ". Nothing was copied."
                )
            for name in CONTENT_TABLES:
                if rows[name]:
                    target_connection.execute(
                        Base.metadata.tables[name].insert(), rows[name]
                    )
                copied[name] = len(rows[name])
            if target.dialect.name == "postgresql":
                for name in SEQUENCE_TABLES:
                    target_connection.execute(
                        text(
                            f"SELECT setval(pg_get_serial_sequence('{name}', 'id'), "
                            f"COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {name}"
                        )
                    )
        return copied
    finally:
        source.dispose()
        target.dispose()


def compare_databases(source_url: str, target_url: str) -> Comparison:
    source = _engine(source_url)
    target = _engine(target_url)
    counts: dict[str, tuple[int, int]] = {}
    differences: list[str] = []
    try:
        source_revision = _revision(source)
        target_revision = _revision(target)
        if source_revision != target_revision:
            differences.append(
                f"alembic_version: source {source_revision}, target {target_revision}"
            )
        with source.connect() as source_connection, target.connect() as target_connection:
            for name in CONTENT_TABLES:
                table = Base.metadata.tables[name]
                key_columns = [column.name for column in table.primary_key.columns]

                def keyed(rows: list[dict]) -> dict[tuple, dict]:
                    return {tuple(row[key] for key in key_columns): row for row in rows}

                source_rows = keyed(_rows(source_connection, name))
                target_rows = keyed(_rows(target_connection, name))
                counts[name] = (len(source_rows), len(target_rows))

                for key in sorted(source_rows.keys() - target_rows.keys()):
                    label = _key_label(name, source_rows[key])
                    differences.append(f"{name} {label}: missing from target")
                for key in sorted(target_rows.keys() - source_rows.keys()):
                    label = _key_label(name, target_rows[key])
                    differences.append(f"{name} {label}: only in target")
                for key in sorted(source_rows.keys() & target_rows.keys()):
                    before = source_rows[key]
                    after = target_rows[key]
                    for column in table.columns.keys():
                        if before[column] != after[column]:
                            differences.append(
                                f"{name} {_key_label(name, before)}: {column} differs, "
                                f"source {before[column]!r}, target {after[column]!r}"
                            )
    finally:
        source.dispose()
        target.dispose()
    return Comparison(counts=counts, differences=differences)


USAGE = "Usage: python -m app.db.transfer copy|compare SOURCE_URL TARGET_URL"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 3 or args[0] not in ("copy", "compare"):
        print(USAGE, file=sys.stderr)
        return 64
    action, source_url, target_url = args

    if action == "copy":
        try:
            copied = copy_rows(source_url, target_url)
        except TransferRefused as error:
            print(f"Refused: {error}", file=sys.stderr)
            return 1
        for name, count in copied.items():
            print(f"{name}: {count} rows copied")
        return 0

    comparison = compare_databases(source_url, target_url)
    for name, (source_count, target_count) in comparison.counts.items():
        print(f"{name}: source {source_count}, target {target_count}")
    for difference in comparison.differences:
        print(difference)
    if comparison.matches:
        print("Match.")
        return 0
    print(f"{len(comparison.differences)} differences.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

Dates and booleans compare as Python values because both sides are read through the same SQLAlchemy column types. A SQLite 1 and a PostgreSQL true both come back as `True`.

- [ ] Step 4: Create `deploy/scripts/transfer-rows.sh`.

```bash
#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 2 ]]; then
    echo "Usage: $0 <source-database-url> <target-database-url>" >&2
    echo "Run from the repo root. The target must be empty and at Alembic head." >&2
    exit 64
fi

if [[ ! -f app/db/transfer.py ]]; then
    echo "Run this from the repo root." >&2
    exit 64
fi

exec uv run python -m app.db.transfer copy "$1" "$2"
```

- [ ] Step 5: Create `deploy/scripts/compare-rows.sh`.

```bash
#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 2 ]]; then
    echo "Usage: $0 <source-database-url> <target-database-url>" >&2
    echo "Run from the repo root. Exits 1 if any row differs." >&2
    exit 64
fi

if [[ ! -f app/db/transfer.py ]]; then
    echo "Run this from the repo root." >&2
    exit 64
fi

exec uv run python -m app.db.transfer compare "$1" "$2"
```

Then make both executable: `chmod +x deploy/scripts/transfer-rows.sh deploy/scripts/compare-rows.sh`.

- [ ] Step 6: Run the tests and the full suite.

Run: `uv run pytest tests/test_transfer.py -v && uv run pytest -q`
Expected: 8 new tests pass, and the full suite passes.

- [ ] Step 7: Try the command line on the local database.

```bash
mkdir -p data/backup-verification
uv run alembic upgrade head
DATABASE_URL=sqlite:///data/backup-verification/copy-check.db uv run alembic upgrade head
bash deploy/scripts/transfer-rows.sh sqlite:///data/resume.db sqlite:///data/backup-verification/copy-check.db
bash deploy/scripts/compare-rows.sh sqlite:///data/resume.db sqlite:///data/backup-verification/copy-check.db
rm data/backup-verification/copy-check.db
```

Expected: the copy prints a count for each of the eight tables, with 7 experiences. The compare prints matching counts and `Match.` and exits 0.

- [ ] Step 8: Lint and commit.

```bash
uv run ruff format . && uv run ruff check .
git add app/db/transfer.py deploy/scripts/transfer-rows.sh deploy/scripts/compare-rows.sh tests/test_transfer.py
git commit -m "feat: copy and compare resume rows between databases"
```

---

### Task 4: PostgreSQL proof test

Files:

- Create: `tests/test_postgres.py`

Interfaces:

- Consumes: `normalize_database_url` from Task 1, the migrations from Task 2, `seed_demo_content` from `app.seed`, the `sample_seed` fixture from `tests/conftest.py`, and `_alembic_config` from `tests/test_migrations.py`.
- Produces: `refuse_real_profiles(connection: Connection) -> None`, the guard Task 8 depends on. Tests that run only when `POSTGRES_TEST_URL` is set.

The spec downgrades "one step." This test downgrades to 20260917_02, the same target the SQLite migration test uses, since that span holds the featured column and the cascade risk. The teardown leaves the database empty at head, which replaces the spec's manual drop in cutover step 4.

- [ ] Step 1: Write `tests/test_postgres.py`.

```python
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
from alembic import command
from sqlalchemy import Connection, Engine, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

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

    with engine.begin() as connection, pytest.raises(RuntimeError, match="Greg Lontok"):
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
        for profile_id, email in ((1, "other@example.com"), (2, "alex.parker@example.com")):
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
        published = connection.execute(
            text("SELECT id FROM profiles WHERE published")
        ).scalars().all()
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

    columns = [column["name"] for column in inspect(postgres_engine).get_columns("experiences")]
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
```

- [ ] Step 2: Run it without PostgreSQL.

Run: `uv run pytest tests/test_postgres.py -v`
Expected: the two guard tests PASS and the three PostgreSQL tests are SKIPPED with the POSTGRES_TEST_URL reason.

- [ ] Step 3: Run the full suite.

Run: `uv run pytest -q`
Expected: all pass, with 3 skipped.

- [ ] Step 4: Lint and commit.

```bash
uv run ruff format . && uv run ruff check .
git add tests/test_postgres.py
git commit -m "test: prove migrations and seed on PostgreSQL when a URL is set"
```

The PostgreSQL tests run for real in Task 8, against the Railway database.

---

### Task 5: Railway configuration

Files:

- Create: `railway.json`
- Create: `tests/test_railway_config.py`

Interfaces:

- Consumes: the `/health` route in `app/main.py` and the `client` fixture in `tests/conftest.py`.
- Produces: `railway.json`, which Railway reads on every deploy from main in Task 7.

The spec's start command "runs Uvicorn through uv." Railpack installs with `uv sync --locked --no-dev` into `/app/.venv` and puts `/app/.venv/bin` on PATH. uv itself may not be in the runtime image, so both commands call the tools from that environment directly.

- [ ] Step 1: Write the failing tests in `tests/test_railway_config.py`.

```python
import json
from pathlib import Path

CONFIG_PATH = Path("railway.json")


def _deploy() -> dict:
    return json.loads(CONFIG_PATH.read_text())["deploy"]


def test_builds_with_railpack() -> None:
    config = json.loads(CONFIG_PATH.read_text())

    assert config["build"]["builder"] == "RAILPACK"


def test_pre_deploy_runs_migrations_and_never_the_seed() -> None:
    assert _deploy()["preDeployCommand"] == ["alembic upgrade head"]
    assert "seed" not in CONFIG_PATH.read_text()


def test_start_command_listens_on_railway_port() -> None:
    start = _deploy()["startCommand"]

    assert start.startswith("uvicorn app.main:app")
    assert "--host 0.0.0.0" in start
    assert "--port $PORT" in start


def test_health_check_path_answers(client) -> None:
    path = _deploy()["healthcheckPath"]

    assert path == "/health"
    assert client.get(path).status_code == 200


def test_restarts_on_failure() -> None:
    assert _deploy()["restartPolicyType"] == "ON_FAILURE"


def test_nothing_overrides_the_uv_lock_install() -> None:
    # Railpack uses pip when requirements.txt exists and a Dockerfile when one exists.
    assert not Path("requirements.txt").exists()
    assert not Path("Dockerfile").exists()
    assert Path("uv.lock").exists()
```

- [ ] Step 2: Run them and confirm they fail.

Run: `uv run pytest tests/test_railway_config.py -v`
Expected: FAIL with `FileNotFoundError: ... 'railway.json'`, except the last test, which passes.

- [ ] Step 3: Create `railway.json`.

```json
{
  "$schema": "https://railway.com/railway.schema.json",
  "build": {
    "builder": "RAILPACK"
  },
  "deploy": {
    "preDeployCommand": ["alembic upgrade head"],
    "startCommand": "uvicorn app.main:app --host 0.0.0.0 --port $PORT",
    "healthcheckPath": "/health",
    "restartPolicyType": "ON_FAILURE"
  }
}
```

- [ ] Step 4: Run the tests and the full suite.

Run: `uv run pytest tests/test_railway_config.py -v && uv run pytest -q`
Expected: all pass.

- [ ] Step 5: Run the start command locally the way Railway will.

```bash
PORT=8123 .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8123 &
sleep 2
curl -s http://127.0.0.1:8123/health
kill %1
```

Expected: `{"status":"ok"}`.

- [ ] Step 6: Lint and commit.

```bash
uv run ruff format . && uv run ruff check .
git add railway.json tests/test_railway_config.py
git commit -m "feat: add Railway build and deploy settings"
```

---

### Task 6: Docs

Files:

- Modify: `README.md`
- Modify: `.env.example`
- Modify: `PRODUCT.md`
- Modify: `tests/test_deploy_assets.py`

Interfaces:

- Consumes: `railway.json` from Task 5 and the wrappers from Task 3.
- Produces: the README sections Tasks 8 to 10 point Greg to.

- [ ] Step 1: Add the failing test to the end of `tests/test_deploy_assets.py`.

```python
def test_readme_documents_railway_and_hand_run_seed() -> None:
    readme = Path("README.md").read_text()

    assert "railway.json" in readme
    assert "deploy/scripts/transfer-rows.sh" in readme
    assert "deploy/scripts/compare-rows.sh" in readme
    assert "DATABASE_URL=\"$RAILWAY_DATABASE_URL\" uv run python -m app.seed" in readme
    assert "never runs the seed" in readme
    assert "reverts" in readme
```

- [ ] Step 2: Run it and confirm it fails.

Run: `uv run pytest tests/test_deploy_assets.py::test_readme_documents_railway_and_hand_run_seed -v`
Expected: FAIL on `"railway.json" in readme`.

- [ ] Step 3: Replace the `## Deployment` section of `README.md`, through the end of the file, with:

````markdown
## Deployment

The site runs on Railway with a Railway PostgreSQL database. `railway.json` holds the service settings, so you can read what Railway does without opening the dashboard. Every push to `main` builds the app from `uv.lock`, runs `alembic upgrade head` as the pre-deploy command, and starts Uvicorn on the port Railway assigns. Railway sends traffic to the new version only once `/health` answers.

A deploy never runs the seed. Code and schema changes ship on push, but content changes are a separate step you run on purpose.

### Update content on Railway

Copy the database's public URL from the Railway Postgres service's Variables tab, where it's called `DATABASE_PUBLIC_URL`. Then edit `app/seed.py`, push, and run the seed once from your laptop:

```bash
export RAILWAY_DATABASE_URL='postgresql://...'
DATABASE_URL="$RAILWAY_DATABASE_URL" uv run python -m app.seed
```

The seed rewrites every seeded row from `app/seed.py`. If a row on Railway was changed by hand and `app/seed.py` doesn't carry the same change, running the seed reverts it.

### Copy rows between databases

`deploy/scripts/transfer-rows.sh` copies every content row from one database to another, keeping the ids. It refuses unless both databases are at the same Alembic head and the target has no rows. `deploy/scripts/compare-rows.sh` reads both and prints every row that differs or is missing, and exits 1 if anything does. Run both from the repo root:

```bash
bash deploy/scripts/transfer-rows.sh sqlite:///data/resume.db "$RAILWAY_DATABASE_URL"
bash deploy/scripts/compare-rows.sh sqlite:///data/resume.db "$RAILWAY_DATABASE_URL"
```

Neither script prints a database URL, since the Railway one carries the password.

### Test against PostgreSQL

`tests/test_postgres.py` runs the migrations and seed against a real PostgreSQL database when `POSTGRES_TEST_URL` is set, and skips otherwise. It drops every table in that database first, and it refuses if any profile other than the fictional sample is there. Point it only at an empty database.

### The Azure VM

[`deploy/README.md`](deploy/README.md) is the runbook for running the site on an Ubuntu Azure VM with Nginx in front. The VM stays as the course's VM reference and as the rollback for the Railway move. Its SQLite backup and restore scripts still apply there.
````

- [ ] Step 4: Replace `.env.example` with:

```bash
# Local SQLite database for development and tests.
DATABASE_URL=sqlite:///./data/resume.db

# Railway sets DATABASE_URL on the deployed service. A Railway PostgreSQL URL
# looks like this, and the app switches it to the psycopg driver on its own:
# DATABASE_URL=postgresql://postgres:PASSWORD@HOST:PORT/railway
```

- [ ] Step 5: In `PRODUCT.md`, replace line 35:

Old:

```markdown
The site runs locally in Codespaces first and then on a single Azure VM, with Uvicorn on `127.0.0.1:8000` behind Nginx. The VM is reached by its public IP and has no DNS name.
```

New:

```markdown
The site runs locally on SQLite and in production on Railway at greglontok.com, with a Railway PostgreSQL database. A push to `main` deploys and runs migrations. Content updates run the seed by hand. The Azure VM it ran on before stays as a reference and a rollback.
```

And replace line 69:

Old:

```markdown
5. The build stays simple enough for a student to read, run, and deploy on one VM.
```

New:

```markdown
5. The build stays simple enough for a student to read, run, and deploy to Railway.
```

- [ ] Step 6: Run the tests and lint.

Run: `uv run pytest -q && uv run ruff format --check . && uv run ruff check .`
Expected: all pass. `test_readme_lists_release_quality_commands` still passes, since the release checklist section above Deployment is unchanged.

- [ ] Step 7: Check the new prose against the voice rules.

```bash
grep -nP "—|;" README.md PRODUCT.md .env.example | grep -v '^\S*:\s*#' || echo "clean"
```

Expected: `clean`, or only hits inside code blocks.

- [ ] Step 8: Commit.

```bash
git add README.md .env.example PRODUCT.md tests/test_deploy_assets.py
git commit -m "docs: describe the Railway deploy, hand-run seed, and row copy"
```

- [ ] Step 9: Merge to main and push, with Greg's go-ahead. Railway deploys from main in Task 7.

```bash
uv run pytest -q
git switch main
git merge --ff-only feat/railway-postgres
git push origin main
```

Expected: tests pass and the push succeeds. Pushing main changes nothing on the VM, which only pulls by hand.

---

### Task 7: Create the Railway project and first deploy

Who: Greg in the Railway dashboard, with the checks run from the laptop.

- [ ] Step 1: Create a Railway project and add a PostgreSQL service from the project canvas.

- [ ] Step 2: Add a web service from the GitHub repo `lontok/career-platform-rehearsal`, branch `main`.

- [ ] Step 3: On the web service's Variables tab, add `DATABASE_URL` with the value `${{Postgres.DATABASE_URL}}`. That reference keeps traffic on Railway's private network. Use the Postgres service's actual name if it isn't `Postgres`.

- [ ] Step 4: On the web service's Settings, Networking section, generate a Railway-provided domain.

- [ ] Step 5: Let the deploy run, then check the logs.

Expected in the build log: Railpack reports `Using uv` and runs `uv sync --locked --no-dev`.
Expected in the pre-deploy log: four Alembic lines ending `Running upgrade 20261006_03 -> 20261006_04`.
Expected in the deploy log: Uvicorn starts on the assigned port and the health check passes.

- [ ] Step 6: Check the Railway-provided domain from the laptop.

```bash
RAILWAY_APP=https://YOUR-SERVICE.up.railway.app
curl -s "$RAILWAY_APP/health"
curl -s -o /dev/null -w "%{http_code}\n" "$RAILWAY_APP/"
curl -s "$RAILWAY_APP/" | grep -o "Career Platform" | head -1
```

Expected: `{"status":"ok"}`, then `200`, then `Career Platform`. No rows exist yet, so the home page shows the default site name and no profile.

---

### Task 8: Run the PostgreSQL proof against Railway

Who: run from the laptop.

- [ ] Step 1: Copy `DATABASE_PUBLIC_URL` from the Railway Postgres service's Variables tab.

```bash
export RAILWAY_DATABASE_URL='postgresql://...'
```

- [ ] Step 2: Run the proof tests.

```bash
POSTGRES_TEST_URL="$RAILWAY_DATABASE_URL" uv run pytest tests/test_postgres.py -v
```

Expected: 5 passed, 0 skipped.

- [ ] Step 3: Confirm the teardown left the database empty at head.

```bash
DATABASE_URL="$RAILWAY_DATABASE_URL" uv run alembic current
DATABASE_URL="$RAILWAY_DATABASE_URL" uv run python - <<'EOF'
from sqlalchemy import create_engine, text
from app.core.config import Settings
from app.db.transfer import CONTENT_TABLES
engine = create_engine(Settings().database_url)
with engine.connect() as connection:
    for table in CONTENT_TABLES:
        print(table, connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one())
EOF
```

Expected: `20261006_04 (head)`, then every table at 0.

---

### Task 9: Copy the VM's rows to Railway with an edited row

Who: Greg picks the edit. The commands run from the laptop.

The edit makes the VM's rows differ from what the seed would produce. If the comparison then matches, the rows on Railway came from the VM. Keep the edit until `app/seed.py` carries it, and don't run the seed against Railway before then.

- [ ] Step 1: Back up the VM's database and copy the backup to the laptop.

```bash
VM='azureuser@20.114.29.82'
KEY=~/.ssh/isba4775_azure
BEFORE=$(ssh -i $KEY $VM 'cd ~/career-platform && ./deploy/scripts/backup-sqlite.sh data/resume.db ~/backups')
echo "$BEFORE"
mkdir -p data/migration-copy
scp -i $KEY "$VM:$BEFORE" data/migration-copy/
```

Expected: a path like `/home/azureuser/backups/resume-20261008T...db`, copied without error. This is the before-edit copy, kept for reference.

- [ ] Step 2: Pick the row and the new location.

Every experience summary is empty on the VM, so the edit goes in `location`, which `/experience` shows after the organization.

```bash
ssh -i $KEY $VM "sqlite3 ~/career-platform/data/resume.db \"SELECT seed_key, organization, location FROM experiences ORDER BY display_order;\""
```

Greg chooses one experience and a new location for it. Pick text that no other row already has, such as `Hollywood, California` in place of `Hollywood, CA`, so the page check below can only match the edited row.

- [ ] Step 3: Make the edit on the VM.

```bash
SEED_KEY='experience:...'
NEW_LOCATION='...'
ssh -i $KEY $VM "sqlite3 ~/career-platform/data/resume.db \"UPDATE experiences SET location = '$NEW_LOCATION' WHERE seed_key = '$SEED_KEY'; SELECT changes();\""
curl -s https://greglontok.com/experience | grep -c "$NEW_LOCATION"
```

Expected: `1` from `changes()`, then a count of at least 1 from the live site. The VM is serving the edited row.

- [ ] Step 4: Back up again and copy that backup to the laptop.

```bash
AFTER=$(ssh -i $KEY $VM 'cd ~/career-platform && ./deploy/scripts/backup-sqlite.sh data/resume.db ~/backups')
scp -i $KEY "$VM:$AFTER" data/migration-copy/
SOURCE="sqlite:///data/migration-copy/$(basename "$AFTER")"
echo "$SOURCE"
```

- [ ] Step 5: Copy the rows to Railway.

```bash
bash deploy/scripts/transfer-rows.sh "$SOURCE" "$RAILWAY_DATABASE_URL"
```

Expected: a count for each of the eight tables, including `experiences: 7 rows copied`, `skills: 4 rows copied`, and `education: 2 rows copied`. A refusal names the reason and writes nothing.

- [ ] Step 6: Compare and keep the output.

```bash
bash deploy/scripts/compare-rows.sh "$SOURCE" "$RAILWAY_DATABASE_URL" | tee data/migration-copy/compare-$(date -u +%Y%m%dT%H%M%SZ).txt
```

Expected: matching counts for every table, then `Match.`, and exit 0. Any difference stops the cutover here. To retry, empty the Railway tables and repeat Steps 5 and 6. Task 8's proof test can't do it, because its guard refuses once Greg Lontok's profile is in the database. Run this instead, which deletes every content row and leaves the schema at head:

```bash
DATABASE_URL="$RAILWAY_DATABASE_URL" uv run python - <<'PY'
from sqlalchemy import create_engine, text
from app.core.config import Settings
from app.db.transfer import CONTENT_TABLES
engine = create_engine(Settings().database_url)
with engine.begin() as connection:
    connection.execute(text("TRUNCATE " + ", ".join(CONTENT_TABLES) + " RESTART IDENTITY"))
    for table in CONTENT_TABLES:
        print(table, connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one())
PY
```

Expected: every table at 0. Only run this against Railway before DNS moves. After cutover, those rows are the live site.

- [ ] Step 7: Check the Railway-provided domain shows the VM's content and the edit.

```bash
for path in / /experience /skills /education; do
  printf "%-12s %s %s\n" "$path" \
    "$(curl -s "$RAILWAY_APP$path" | md5)" \
    "$(curl -s "https://greglontok.com$path" | md5)"
done
curl -s "$RAILWAY_APP/experience" | grep -c "$NEW_LOCATION"
```

Expected: matching hashes for each path, and a count of at least 1 for the new location. If a hash differs, compare the two pages by eye before going on. The static-file version hash in the page can differ if the VM's checkout isn't at the same commit as main.

---

### Task 10: Cloudflare cutover, DNS only

Who: Greg in the Cloudflare dashboard, with the checks run from the laptop.

The Cloudflare change is four records and nothing else: a CNAME and a TXT record for the root, and a CNAME and a TXT record for www. Leave every TTL, the proxy setting on other records, the SSL mode, and redirects as they are.

- [ ] Step 1: Record the current DNS so rollback has exact values.

```bash
dig +noall +answer greglontok.com A
dig +noall +answer www.greglontok.com A
```

Expected: both names as A records at `20.114.29.82`. Save both lines, and note in the Cloudflare dashboard whether each record is proxied.

- [ ] Step 2: In Railway, add `greglontok.com` and `www.greglontok.com` as two custom domains on the web service. Railway shows a CNAME value and a TXT record for each. Note which value belongs to which name, since they differ.

- [ ] Step 3: In Cloudflare, under DNS and then Records for greglontok.com:

1. Delete the root A record that points at `20.114.29.82`.
2. Add a CNAME record. Name `@`, target Railway's CNAME value for `greglontok.com`, proxy status DNS only, the grey cloud.
3. Add the TXT record Railway shows for `greglontok.com`.
4. Delete the www A record that points at `20.114.29.82`.
5. Add a CNAME record. Name `www`, target Railway's CNAME value for `www.greglontok.com`, proxy status DNS only, the grey cloud.
6. Add the TXT record Railway shows for `www.greglontok.com`.

- [ ] Step 4: Wait for Railway to show both domains verified and their certificates issued. Then check both names from the laptop.

```bash
for host in greglontok.com www.greglontok.com; do
  echo "== $host"
  dig +short "$host"
  curl -sI "https://$host/" | grep -i -E "^HTTP|railway"
  curl -s -o /dev/null -w "%{http_code} -> %{redirect_url}\n" "http://$host/"
  echo | openssl s_client -connect "$host:443" -servername "$host" 2>/dev/null | openssl x509 -noout -subject -issuer -enddate
  curl -s "https://$host/experience" | grep -c "$NEW_LOCATION"
  curl -s "https://$host/health"; echo
done
```

Expected for each name: `dig` returns Railway's target, not `20.114.29.82`. The headers show `HTTP/2 200` and a Railway header. Plain http answers `301` to the https address on the same name, not to the other name. The certificate's subject is that name. The new location appears, and `/health` returns `{"status":"ok"}`. If the old IP still answers, wait for the old records' TTL and check again.

- [ ] Step 5: Run the comparison once more.

```bash
bash deploy/scripts/compare-rows.sh "$SOURCE" "$RAILWAY_DATABASE_URL"
```

Expected: `Match.` and exit 0.

- [ ] Step 6: Confirm the VMs are as they were.

```bash
az vm list -d --query "[].{name:name, rg:resourceGroup, power:powerState}" -o table
```

Expected: both VMs listed and running. Nothing in this plan stops or deletes either one.

Rollback, at any point after Step 3: in Cloudflare, delete both CNAMEs and add back the root and www A records to `20.114.29.82`, with the proxy settings recorded in Step 1. Roll back both names together. The VM is still running and its certificate covers both names, so it serves again once the CNAMEs' TTL passes.

---

## Spec coverage

| Spec section | Task |
| --- | --- |
| 5.1 driver, URL rewrite, index, migration 02 | 1, 2 |
| 5.2 railway.json, pre-deploy migrations only, seed by hand | 5, 6 |
| 5.3 transfer and comparison scripts, edited row | 3, 9 |
| 5.4 PostgreSQL proof test | 4, 8 |
| 5.5 Railway project and cutover steps 1 to 10 | 7, 8, 9, 10 |
| 5.6 README, .env.example, PRODUCT.md | 6 |
| 6 failure handling and rollback | 3, 9, 10 |
| 7 testing | 1 to 5 |
| 8 acceptance criteria | 10 checks 1, 2, 6. Task 7 checks 3. Task 6 checks 4 and 7. Task 8 checks 5. |
