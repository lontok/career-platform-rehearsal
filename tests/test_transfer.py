from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from alembic import command
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
    for script in (
        "deploy/scripts/transfer-rows.sh",
        "deploy/scripts/compare-rows.sh",
    ):
        result = subprocess.run(
            ["bash", script], check=False, capture_output=True, text=True
        )
        assert result.returncode == 64
        assert "Usage:" in result.stderr


def test_a_connection_failure_raises_instead_of_reading_as_unmigrated(
    source_url,
) -> None:
    unreachable = "postgresql://user:secret@127.0.0.1:1/railway"

    with pytest.raises(OperationalError):
        copy_rows(source_url, unreachable)
    with pytest.raises(OperationalError):
        compare_databases(source_url, unreachable)
