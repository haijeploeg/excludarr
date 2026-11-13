import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("make") is None or os.name == "nt", reason="Requires POSIX make and sh"
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def make_dev(tmp_path):
    docker = tmp_path / "docker"
    calls = tmp_path / "calls.jsonl"
    docker.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        'with open(os.environ["DOCKER_CALLS"], "a") as stream:\n'
        '    stream.write(json.dumps(sys.argv[1:]) + "\\n")\n'
        'sys.exit(int(os.environ.get("DOCKER_EXIT", "0")))\n'
    )
    docker.chmod(0o755)

    def run(*args, exit_code=0):
        calls.unlink(missing_ok=True)
        result = subprocess.run(
            ["make", "--no-print-directory", *args],
            cwd=ROOT,
            env=os.environ
            | {
                "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
                "DOCKER_CALLS": str(calls),
                "DOCKER_EXIT": str(exit_code),
            },
            capture_output=True,
            text=True,
            check=False,
        )
        commands = (
            [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []
        )
        return result, commands

    return run


def test_dev_uses_single_launcher_and_preserves_quoted_rule(make_dev):
    result, calls = make_dev("dev", 'ARGS=run --rule "Tag big movies" --yes')
    assert result.returncode == 0
    assert calls == [
        [
            "compose",
            "-p",
            "excludarr-dev",
            "run",
            "--rm",
            "--entrypoint",
            "python",
            "tools",
            "-m",
            "dev.cli",
            "run",
            "--rule",
            "Tag big movies",
            "--yes",
        ]
    ]


def test_dev_shell_uses_the_same_launcher(make_dev):
    result, calls = make_dev("dev-shell")
    assert result.returncode == 0
    assert calls == [
        [
            "compose",
            "-p",
            "excludarr-dev",
            "run",
            "--rm",
            "--entrypoint",
            "python",
            "tools",
            "-m",
            "dev.cli",
            "--shell",
        ]
    ]


def test_dev_refuses_obsolete_config_selection(make_dev):
    result, calls = make_dev("dev", "CONFIG=actions")
    assert result.returncode != 0
    assert calls == []


def test_dev_feed_and_daemon_share_the_manual_stack(make_dev):
    result, calls = make_dev("dev-feed", "LIST=movies-strict")
    assert result.returncode == 0
    assert calls[0][-4:] == ["-m", "dev.cli", "--feed", "movies-strict"]
    result, calls = make_dev("dev-daemon")
    assert result.returncode == 0
    assert calls == [
        [
            "compose",
            "-p",
            "excludarr-dev",
            "--profile",
            "daemon",
            "up",
            "-d",
            "--no-deps",
            "--force-recreate",
            "excludarr",
        ]
    ]


def test_lifecycle_preserves_volumes_and_seed_stops_daemon(make_dev):
    result, calls = make_dev("dev-down")
    assert result.returncode == 0
    assert calls == [["compose", "-p", "excludarr-dev", "--profile", "*", "down"]]
    result, calls = make_dev("dev-seed")
    assert result.returncode == 0
    assert calls == [
        ["compose", "-p", "excludarr-dev", "stop", "excludarr"],
        ["compose", "-p", "excludarr-dev", "run", "--rm", "tools", "seed"],
    ]


def test_failed_docker_command_stops_dependent_operations(make_dev):
    result, calls = make_dev("dev-check", exit_code=7)
    assert result.returncode != 0
    assert calls == [["compose", "-p", "excludarr-dev", "stop", "excludarr"]]
