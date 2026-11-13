import os
from pathlib import Path

import pytest
import yaml

from excludarr.conditions import LEAVES, leaves
from excludarr.config import load_config

ROOT = Path(__file__).resolve().parents[1]


def test_manual_config_covers_user_features_with_preview_defaults(monkeypatch):
    for name in (
        "RADARR_API_KEY",
        "SONARR_API_KEY",
        "PLEX_TOKEN",
        "TAUTULLI_API_KEY",
        "SEERR_API_KEY",
        "LIST_PROXY_API_KEY",
        "DEV_PLEX_USER",
    ):
        monkeypatch.setenv(name, "test-value")
    config, _ = load_config(ROOT / "dev/excludarr.yml")
    assert all(rule.preview for rule in config.rules)
    assert {rule.action for rule in config.rules} == {
        "delete",
        "delete_files",
        "monitor",
        "unmonitor",
        "tag",
        "import_exclusion",
    }
    assert {rule.level for rule in config.rules} >= {"movie", "series", "season", "episode"}
    used = {
        leaf.name
        for rule in config.rules
        for condition in [rule.when, *rule.unless]
        for leaf in leaves(condition)
    }
    assert used == set(LEAVES)
    assert config.profile.locale == "nl_NL"
    assert config.profile.providers == ["Netflix"]
    assert config.database == "sqlite:////config/manual.db"
    assert any(rule.grace_period and rule.leaving_soon_collection for rule in config.rules)
    assert any(rule.schedule for rule in config.rules)
    assert {rule.on_unknown for rule in config.list_proxy.lists.values()} == {"include", "exclude"}


def test_launcher_injects_private_keys_without_overwriting_optional_cloud_env(
    monkeypatch, tmp_path
):
    from dev import cli, stack

    monkeypatch.setattr(stack, "CONFIG", tmp_path)
    monkeypatch.setattr(
        stack,
        "credentials",
        lambda: {
            "radarr": "local-r",
            "sonarr": "local-s",
            "plex": "local-p",
            "tautulli": "local-t",
            "seerr": "local-q",
            "feed": "local-f",
        },
    )
    (tmp_path / "state.json").write_text('{"plex":{"username":"test-viewer"}}')
    monkeypatch.setenv("TMDB_READ_TOKEN", "optional-test-token")
    monkeypatch.setenv("RADARR_API_KEY", "wrong-host-value")
    env = cli.environment()
    assert env["RADARR_API_KEY"] == "local-r"
    assert env["DEV_PLEX_USER"] == "test-viewer"
    assert env["TMDB_READ_TOKEN"] == "optional-test-token"
    assert env["EXCLUDARR_CONFIG"] == "/config/user/excludarr.yml"


@pytest.mark.parametrize(
    "change", [("url", "http://personal-radarr:7878"), ("database", "sqlite:////config/actions.db")]
)
def test_launcher_refuses_foreign_endpoints_or_shared_test_state(monkeypatch, tmp_path, change):
    from dev import cli

    document = {
        "integrations": {"radarr": {"url": "http://radarr:7878", "api_key": "fake"}},
        "database": "sqlite:////config/manual.db",
    }
    key, value = change
    if key == "url":
        document["integrations"]["radarr"]["url"] = value
    else:
        document[key] = value
    path = tmp_path / "config.yml"
    path.write_text(yaml.safe_dump(document))
    with pytest.raises(cli.SetupError):
        cli.validate_config(path)


@pytest.mark.parametrize(
    "args", [["--config", "/tmp/other.yml", "run"], ["--config=/tmp/other.yml", "run"]]
)
def test_launcher_refuses_config_override_before_exec(monkeypatch, args):
    from dev import cli

    monkeypatch.setattr(cli.sys, "argv", ["dev.cli", *args])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1


def test_launcher_reports_config_errors_without_credential_values(monkeypatch, capsys):
    from dev import cli
    from excludarr.config import ConfigError

    monkeypatch.setattr(cli.sys, "argv", ["dev.cli", "preview"])
    monkeypatch.setenv("RADARR_API_KEY", "private-test-value")
    monkeypatch.setattr(cli, "environment", lambda: {"RADARR_API_KEY": "private-test-value"})

    def invalid():
        raise ConfigError("rules.0.when: invalid duration private-test-value")

    monkeypatch.setattr(cli, "validate_config", invalid)
    with pytest.raises(SystemExit):
        cli.main()
    output = capsys.readouterr().err
    assert "rules.0.when" in output
    assert "private-test-value" not in output


def test_shell_routes_commands_through_launcher(monkeypatch):
    import os

    from dev import cli

    captured = {}

    class Launched(Exception):
        pass

    monkeypatch.setattr(cli.sys, "argv", ["dev.cli", "--shell"])
    monkeypatch.setattr(cli, "environment", lambda: dict(os.environ))
    monkeypatch.setattr(cli, "validate_config", lambda: None)
    monkeypatch.setattr(cli.stack, "verify_stack", lambda **kwargs: {})

    def execute(program, args, env):
        captured.update(program=program, args=args, env=env)
        raise Launched

    monkeypatch.setattr(cli.os, "execvpe", execute)
    with pytest.raises(Launched):
        cli.main()
    assert captured["program"] == "bash"
    assert captured["args"] == ["bash"]
    wrapper_dir = str(ROOT / "dev/bin")
    assert captured["env"]["PATH"].split(os.pathsep)[0] == wrapper_dir


@pytest.mark.skipif(os.name == "nt", reason="Requires POSIX shell")
def test_shell_wrapper_preserves_args_for_config_override_guard(tmp_path):
    import json
    import os
    import subprocess
    import sys

    python = tmp_path / "python"
    python.write_text(f"#!{sys.executable}\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n")
    python.chmod(0o755)
    result = subprocess.run(
        [str(ROOT / "dev/bin/excludarr"), "--config", "/tmp/other.yml", "run"],
        env=os.environ | {"PATH": str(tmp_path)},
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == ["-m", "dev.cli", "--config", "/tmp/other.yml", "run"]


def test_feed_waits_for_server_and_initial_snapshot(monkeypatch, respx_mock, capsys):
    import time
    from types import SimpleNamespace

    import httpx
    from pydantic import SecretStr

    from dev import cli

    monkeypatch.setattr(cli.sys, "argv", ["dev.cli", "--feed", "movies"])
    monkeypatch.setattr(cli, "environment", dict)
    monkeypatch.setattr(cli.stack, "verify_stack", lambda **kwargs: {})
    proxy = SimpleNamespace(lists={"movies": object()}, api_key=SecretStr("config-test-key"))
    monkeypatch.setattr(cli, "validate_config", lambda: SimpleNamespace(list_proxy=proxy))
    monkeypatch.setattr(time, "sleep", lambda _: None)
    route = respx_mock.get(
        "http://excludarr:8989/lists/movies", params={"apikey": "config-test-key"}
    )
    route.side_effect = [
        httpx.ConnectError("starting"),
        httpx.Response(503),
        httpx.Response(200, json=[{"imdb_id": "tt0137523"}]),
    ]
    cli.main()
    assert "tt0137523" in capsys.readouterr().out


def test_feed_bootstrap_wait_has_deadline_and_hides_key(monkeypatch, respx_mock, capsys):
    import time
    from types import SimpleNamespace

    from pydantic import SecretStr

    from dev import cli

    monkeypatch.setattr(cli.sys, "argv", ["dev.cli", "--feed", "movies"])
    monkeypatch.setattr(cli, "environment", dict)
    monkeypatch.setattr(cli.stack, "verify_stack", lambda **kwargs: {})
    proxy = SimpleNamespace(lists={"movies": object()}, api_key=SecretStr("config-test-key"))
    monkeypatch.setattr(cli, "validate_config", lambda: SimpleNamespace(list_proxy=proxy))
    clock = iter([0, 0, 31])
    monkeypatch.setattr(time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(time, "sleep", lambda _: None)
    respx_mock.get("http://excludarr:8989/lists/movies").respond(503)
    with pytest.raises(SystemExit):
        cli.main()
    output = capsys.readouterr().err
    assert "not ready" in output
    assert "config-test-key" not in output
