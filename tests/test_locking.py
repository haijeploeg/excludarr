import queue
import subprocess
import sys
from pathlib import Path
from threading import Thread

import pytest

from excludarr.config import ConfigError
from excludarr.locking import (
    WorkBusy,
    daemon_lock,
    execution_lock,
    require_daemon_database,
    sqlite_path,
)


@pytest.mark.parametrize("kind", ["daemon", "execution"])
def test_process_exclusion_and_crash_release(tmp_path, kind):
    url = f"sqlite:///{tmp_path}/db"
    script = """import sys
from excludarr.locking import daemon_lock, execution_lock
with (daemon_lock(sys.argv[1]) if sys.argv[2] == 'daemon' else execution_lock(sys.argv[1])):
    print('ready', flush=True)
    sys.stdin.read(1)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script, url, kind],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    ready = queue.Queue()
    Thread(target=lambda: ready.put(process.stdout.readline()), daemon=True).start()
    try:
        assert ready.get(timeout=8).strip() == "ready"
        with pytest.raises(WorkBusy), daemon_lock(url) if kind == "daemon" else execution_lock(url):
            pytest.fail("second process acquired owned lock")
        process.terminate()
        process.wait(timeout=8)
        with daemon_lock(url) if kind == "daemon" else execution_lock(url):
            pass
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=8)


def test_aliases_and_noop_manual_database(tmp_path, monkeypatch):
    database = tmp_path / "db"
    database.touch()
    alias = tmp_path / "alias"
    alias.symlink_to(database)
    monkeypatch.chdir(tmp_path)
    assert sqlite_path("sqlite:///db") == database
    assert sqlite_path(f"sqlite:///{alias}") == database
    with (
        execution_lock("sqlite:///db"),
        pytest.raises(WorkBusy),
        execution_lock(f"sqlite:///{alias}"),
    ):
        pass
    assert Path(str(database) + ".execution.lock").exists()
    with execution_lock("sqlite:///:memory:"):
        pass


@pytest.mark.parametrize(
    "url",
    [
        "sqlite:///:memory:",
        "sqlite://",
        "postgresql://localhost/db",
        "sqlite:///file:memdb?mode=memory&uri=true",
    ],
)
def test_daemon_requires_local_file_database(url):
    assert sqlite_path(url) is None
    with pytest.raises(ConfigError):
        require_daemon_database(url)


@pytest.mark.parametrize("options", ["?timeout=30", "?check_same_thread=false"])
def test_sqlite_connection_options_share_the_same_lock(tmp_path, options):
    url = f"sqlite:///{tmp_path}/db"
    assert sqlite_path(url + options) == sqlite_path(url)
    assert require_daemon_database(url + options) == sqlite_path(url)
    with execution_lock(url), pytest.raises(WorkBusy), execution_lock(url + options):
        pass


def test_local_file_uri_also_contends_but_is_not_daemon_eligible(tmp_path):
    url = f"sqlite:///{tmp_path}/db"
    uri = f"sqlite:///file:{tmp_path}/db?mode=rwc&uri=true"
    assert sqlite_path(uri) == sqlite_path(url)
    with execution_lock(url), pytest.raises(WorkBusy), execution_lock(uri):
        pass
    with pytest.raises(ConfigError):
        require_daemon_database(uri)
