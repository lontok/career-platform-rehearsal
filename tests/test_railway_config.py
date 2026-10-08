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
