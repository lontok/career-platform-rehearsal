import sqlite3
import stat
import subprocess
from pathlib import Path


def test_backup_creates_a_restricted_verified_database_copy(tmp_path: Path) -> None:
    source_database = tmp_path / "source.db"
    backup_directory = tmp_path / "backups"
    with sqlite3.connect(source_database) as connection:
        connection.execute("CREATE TABLE records (value TEXT NOT NULL)")
        connection.execute("INSERT INTO records VALUES ('public resume data')")

    result = subprocess.run(
        [
            "bash",
            "deploy/scripts/backup-sqlite.sh",
            str(source_database),
            str(backup_directory),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    backup_file = Path(result.stdout.strip())
    assert backup_file.is_file()
    assert stat.S_IMODE(backup_file.stat().st_mode) == 0o600
    with sqlite3.connect(backup_file) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def test_systemd_binds_uvicorn_to_loopback_only() -> None:
    service = Path("deploy/systemd/career-platform.service").read_text()

    assert "--host 127.0.0.1" in service
    assert "--port 8000" in service


def test_nginx_proxies_to_loopback() -> None:
    config = Path("deploy/nginx/career-platform.conf").read_text()

    assert "proxy_pass http://127.0.0.1:8000;" in config


def test_readme_lists_release_quality_commands() -> None:
    readme = Path("README.md").read_text()

    assert "uv run ruff check ." in readme
    assert "uv run pytest -q" in readme
    assert "backup-sqlite.sh" in readme


def test_readme_documents_railway_and_hand_run_seed() -> None:
    readme = Path("README.md").read_text()

    assert "railway.json" in readme
    assert "deploy/scripts/transfer-rows.sh" in readme
    assert "deploy/scripts/compare-rows.sh" in readme
    assert 'DATABASE_URL="$RAILWAY_DATABASE_URL" uv run python -m app.seed' in readme
    assert "never runs the seed" in readme
    assert "reverts" in readme
