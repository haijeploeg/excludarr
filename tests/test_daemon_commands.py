import json

import pytest
import yaml
from typer.testing import CliRunner

from excludarr.cli import app


def config_file(tmp_path, **extra):
    data = {
        "integrations": {"radarr": {"url": "http://r", "api_key": "private-key"}},
        "scheduler": {"timezone": "Europe/Amsterdam"},
        "rules": [
            {
                "name": "Example",
                "target": "radarr",
                "schedule": "0 2 * * *",
                "action": "tag",
                "tag": "review",
                "when": {"year": {"min": 2000}},
            }
        ],
        **extra,
    }
    path = tmp_path / "config.yml"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


@pytest.mark.parametrize("format", ["json", "yaml"])
def test_status_offline_is_local(tmp_path, monkeypatch, format):
    path = config_file(tmp_path)

    def forbid(*args):
        pytest.fail("status must not create integration clients")

    monkeypatch.setattr("excludarr.facts.Clients.from_config", forbid)
    result = CliRunner().invoke(app, ["--config", str(path), "schedule", "status", "-o", format])
    assert result.exit_code == 0, result.output
    doc = json.loads(result.stdout) if format == "json" else yaml.safe_load(result.stdout)
    assert doc["summary"]["daemon"] == "offline"
    assert doc["items"][0]["name"] == "Example"
    assert doc["items"][0]["next_due"] is None
    assert doc["items"][0]["timezone"] == "Europe/Amsterdam"


def test_daemon_startup_and_no_secret(tmp_path, monkeypatch):
    path = config_file(tmp_path)
    monkeypatch.setattr("excludarr.daemon.run_daemon", lambda *a, **kw: None)
    result = CliRunner().invoke(app, ["--config", str(path), "daemon"], terminal_width=120)
    assert result.exit_code == 0, result.output
    assert "Europe/Amsterdam" in result.stderr
    assert "Example" in result.stderr
    assert "0 2 * * *" in result.stderr
    assert "private-key" not in result.output


def test_daemon_rejects_memory_database(tmp_path):
    path = config_file(tmp_path, database="sqlite:///:memory:")
    result = CliRunner().invoke(app, ["--config", str(path), "daemon"])
    assert result.exit_code == 1
    assert "file-backed SQLite" in result.output


def test_daemon_rejects_second_owner(tmp_path):
    from excludarr.locking import daemon_lock

    path = config_file(tmp_path)
    with daemon_lock(f"sqlite:///{tmp_path}/excludarr.db"):
        result = CliRunner().invoke(app, ["--config", str(path), "daemon"])
    assert result.exit_code == 1
    assert "active" in result.output


def test_stale_status_does_not_override_singleton(tmp_path):
    from datetime import UTC, datetime, timedelta

    from excludarr.config import load_config
    from excludarr.jobs import configured_jobs
    from excludarr.locking import daemon_lock
    from excludarr.storage.repo import Repo

    path = config_file(tmp_path)
    config, _ = load_config(path)
    url = f"sqlite:///{tmp_path}/excludarr.db"
    repo = Repo(url)
    repo.scheduler_start(
        "old",
        configured_jobs(config),
        config.scheduler.timezone,
        datetime.now(UTC) - timedelta(minutes=1),
    )
    with daemon_lock(url):
        result = CliRunner().invoke(
            app, ["--config", str(path), "schedule", "status", "-o", "json"]
        )
        assert json.loads(result.stdout)["summary"]["daemon"] == "stale"
        second = CliRunner().invoke(app, ["--config", str(path), "daemon"])
        assert second.exit_code == 1
    assert repo.scheduler_status()["daemon"]["instance"] == "old"


@pytest.mark.parametrize("width", [80, 120])
def test_active_status_uses_local_offset(tmp_path, width):
    from datetime import UTC, datetime

    from excludarr.config import load_config
    from excludarr.jobs import configured_jobs
    from excludarr.storage.repo import Repo

    path = config_file(tmp_path)
    config, _ = load_config(path)
    repo = Repo(f"sqlite:///{tmp_path}/excludarr.db")
    repo.scheduler_start("one", configured_jobs(config), "Europe/Amsterdam", datetime.now(UTC))
    due = datetime(2027, 3, 29, tzinfo=UTC)
    repo.scheduler_update(
        "one",
        [
            {
                "kind": "rule",
                "name": "Example",
                "state": "idle",
                "next_due": due,
                "pending_due": None,
                "last_dispatched_due": None,
            }
        ],
    )
    command = ["--config", str(path), "schedule", "status"]
    table = CliRunner().invoke(app, command, terminal_width=width)
    assert table.exit_code == 0, table.output
    assert "Example" in table.stdout
    assert "+0200" in table.stdout
    doc = json.loads(CliRunner().invoke(app, command + ["-o", "json"]).stdout)
    assert doc["items"][0]["next_due"] == "2027-03-29T00:00:00+00:00"
    assert doc["summary"]["daemon"] == "active"
