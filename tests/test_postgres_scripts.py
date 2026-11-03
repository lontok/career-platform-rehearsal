"""Tests for the PostgreSQL backup and restore scripts.

The PostgreSQL client tools are replaced with small bash stubs on PATH, so these
tests need no database and check only what the scripts decide to do.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

BACKUP_SCRIPT = "deploy/scripts/backup-postgres.sh"
RESTORE_SCRIPT = "deploy/scripts/restore-postgres.sh"
RESUME_TABLES = (
    "alembic_version",
    "profiles",
    "projects",
    "experiences",
    "skills",
    "education",
)
FAKE_URL = "postgresql://user:secret@db.example:5432/resume"

LOG_CALL = 'printf "%s %s\\n" "$(basename "$0")" "$*" >> "$CALLS_LOG"\n'
WRITE_DUMP = 'for arg in "$@"; do case "$arg" in --file=*) printf dump > "${arg#--file=}";; esac; done\n'


def stub_path(tmp_path: Path, scripts: dict[str, str]) -> dict[str, str]:
    """Write each script as an executable stub and return an environment that finds them first."""
    bin_directory = tmp_path / "bin"
    bin_directory.mkdir(exist_ok=True)
    for name, body in scripts.items():
        stub = bin_directory / name
        stub.write_text("#!/usr/bin/env bash\n" + LOG_CALL + body)
        stub.chmod(0o755)
    environment = dict(os.environ)
    environment["PATH"] = f"{bin_directory}{os.pathsep}{environment['PATH']}"
    environment["CALLS_LOG"] = str(tmp_path / "calls.log")
    return environment


def pg_restore_listing(tables: tuple[str, ...]) -> str:
    lines = "".join(
        f'echo "1; 0 0 TABLE DATA public {table} postgres"\n' for table in tables
    )
    return f'if [[ "$1" == "--list" ]]; then\n{lines}fi\n'


def calls(tmp_path: Path) -> list[str]:
    log = tmp_path / "calls.log"
    return log.read_text().splitlines() if log.exists() else []


def run(script: str, *arguments: str, environment: dict[str, str]):
    return subprocess.run(
        ["bash", script, *arguments],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def test_backup_keeps_a_private_verified_dump(tmp_path: Path) -> None:
    environment = stub_path(
        tmp_path,
        {"pg_dump": WRITE_DUMP, "pg_restore": pg_restore_listing(RESUME_TABLES)},
    )
    backup_directory = tmp_path / "backups"

    result = run(
        BACKUP_SCRIPT, FAKE_URL, str(backup_directory), environment=environment
    )

    assert result.returncode == 0, result.stderr
    backup_file = Path(result.stdout.strip())
    assert backup_file.parent == backup_directory
    assert backup_file.name.startswith("resume-")
    assert backup_file.suffix == ".dump"
    assert stat.S_IMODE(backup_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(backup_directory.stat().st_mode) == 0o700


def test_backup_deletes_a_dump_missing_a_table(tmp_path: Path) -> None:
    environment = stub_path(
        tmp_path,
        {"pg_dump": WRITE_DUMP, "pg_restore": pg_restore_listing(("alembic_version",))},
    )
    backup_directory = tmp_path / "backups"

    result = run(
        BACKUP_SCRIPT, FAKE_URL, str(backup_directory), environment=environment
    )

    assert result.returncode == 65
    assert "profiles" in result.stderr
    assert list(backup_directory.iterdir()) == []


def test_backup_deletes_the_file_when_pg_dump_fails(tmp_path: Path) -> None:
    environment = stub_path(
        tmp_path,
        {
            "pg_dump": WRITE_DUMP + "exit 1\n",
            "pg_restore": pg_restore_listing(RESUME_TABLES),
        },
    )
    backup_directory = tmp_path / "backups"

    result = run(
        BACKUP_SCRIPT, FAKE_URL, str(backup_directory), environment=environment
    )

    assert result.returncode != 0
    assert list(backup_directory.iterdir()) == []


def test_backup_usage_error(tmp_path: Path) -> None:
    environment = stub_path(tmp_path, {})

    result = run(BACKUP_SCRIPT, FAKE_URL, environment=environment)

    assert result.returncode == 64


def test_restore_refuses_a_target_with_tables(tmp_path: Path) -> None:
    environment = stub_path(tmp_path, {"psql": "echo 3\n", "pg_restore": ""})
    backup_file = tmp_path / "resume.dump"
    backup_file.write_text("dump")

    result = run(RESTORE_SCRIPT, str(backup_file), FAKE_URL, environment=environment)

    assert result.returncode == 73
    assert "already has 3 tables" in result.stderr
    assert not any(call.startswith("pg_restore") for call in calls(tmp_path))


def test_restore_loads_an_empty_target_in_one_transaction(tmp_path: Path) -> None:
    environment = stub_path(tmp_path, {"psql": "echo 0\n", "pg_restore": ""})
    backup_file = tmp_path / "resume.dump"
    backup_file.write_text("dump")

    result = run(RESTORE_SCRIPT, str(backup_file), FAKE_URL, environment=environment)

    assert result.returncode == 0, result.stderr
    [restore_call] = [call for call in calls(tmp_path) if call.startswith("pg_restore")]
    for flag in ("--single-transaction", "--exit-on-error", "--no-owner"):
        assert flag in restore_call
    assert str(backup_file) in restore_call


def test_restore_missing_backup_file(tmp_path: Path) -> None:
    environment = stub_path(tmp_path, {"psql": "echo 0\n", "pg_restore": ""})

    result = run(
        RESTORE_SCRIPT,
        str(tmp_path / "missing.dump"),
        FAKE_URL,
        environment=environment,
    )

    assert result.returncode == 66
