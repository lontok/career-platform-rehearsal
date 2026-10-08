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
from sqlalchemy import Connection, Engine, create_engine, func, inspect, select, text

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
    # A missing version table means an unmigrated database. A failed connection
    # raises instead, so a mistyped URL never reads as "at None".
    with engine.connect() as connection:
        if not inspect(connection).has_table("alembic_version"):
            return None
        return connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one_or_none()


def _rows(connection: Connection, name: str) -> list[dict]:
    table = Base.metadata.tables[name]
    statement = select(table).order_by(*table.primary_key.columns)
    return [dict(row) for row in connection.execute(statement).mappings()]


def _key_label(table_name: str, row: dict) -> str:
    table = Base.metadata.tables[table_name]
    return ", ".join(
        f"{column.name}={row[column.name]}" for column in table.primary_key.columns
    )


def _keyed(table_name: str, rows: list[dict]) -> dict[tuple, dict]:
    table = Base.metadata.tables[table_name]
    key_columns = [column.name for column in table.primary_key.columns]
    return {tuple(row[key] for key in key_columns): row for row in rows}


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
        with (
            source.connect() as source_connection,
            target.connect() as target_connection,
        ):
            for name in CONTENT_TABLES:
                table = Base.metadata.tables[name]
                source_rows = _keyed(name, _rows(source_connection, name))
                target_rows = _keyed(name, _rows(target_connection, name))
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
                    for column in (column.name for column in table.columns):
                        if before[column] != after[column]:
                            differences.append(
                                f"{name} {_key_label(name, before)}: "
                                f"{column} differs, "
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
