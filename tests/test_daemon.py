from datetime import UTC, datetime, timedelta
from threading import Event, Thread

import pytest

from excludarr.config import Config, ConfigError
from excludarr.daemon import execute_batch, run_daemon
from excludarr.facts import Clients
from excludarr.jobs import PendingJob, configured_jobs
from excludarr.locking import execution_lock
from excludarr.storage.repo import Repo

NOW = datetime(2026, 11, 11, 10, tzinfo=UTC)


def setup(tmp_path, rules=True):
    config = Config.model_validate(
        {
            "database": f"sqlite:///{tmp_path}/db",
            "integrations": {"radarr": {"url": "http://r", "api_key": "private-key"}},
            "rules": [
                {
                    "name": name,
                    "target": "radarr",
                    "action": "tag",
                    "tag": "example",
                    "schedule": "* * * * *",
                    "when": {"year": {"min": 2000}},
                }
                for name in ("A", "B", "C")
            ]
            if rules
            else [],
        }
    )
    repo = Repo(config.database)
    repo.scheduler_start("one", configured_jobs(config), "UTC", NOW)
    return config, repo


def test_rule_exception_preserves_completed_and_pending(tmp_path, monkeypatch):
    from excludarr.items import MediaItem

    config, repo = setup(tmp_path)
    monkeypatch.setattr(Clients, "from_config", classmethod(lambda cls, c: cls()))
    monkeypatch.setattr(
        "excludarr.engine.build_radarr_items",
        lambda _: [MediaItem("radarr:movie:1", "movie", "Example", "Example", 1, year=2020)],
    )
    from excludarr import engine

    original = engine.evaluate_rule

    def evaluation(rule, *a, **kw):
        if rule.name == "B":
            raise RuntimeError("private-key must be redacted")
        return original(rule, *a, **kw)

    monkeypatch.setattr(engine, "evaluate_rule", evaluation)
    jobs = [PendingJob(("rule", name), NOW) for name in ("A", "B", "C")]
    result = execute_batch(config, repo, "one", jobs, Event(), lambda: NOW)
    assert result.completed == {("rule", "A"): "success", ("rule", "B"): "failed"}
    assert result.unstarted == [jobs[2]]
    rows = repo.scheduler_status()["jobs"]
    assert rows[0]["last_execution"]["outcome"] == "success"
    assert "private-key" not in rows[1]["last_execution"]["error"]
    assert rows[2]["last_execution"] is None


def test_busy_and_preflight_failure(tmp_path, monkeypatch):
    config, repo = setup(tmp_path)
    monkeypatch.setattr(Clients, "from_config", classmethod(lambda cls, c: cls()))
    jobs = [PendingJob(("rule", "A"), NOW)]
    with execution_lock(config.database):
        result = execute_batch(config, repo, "one", jobs, Event(), lambda: NOW)
    assert result.unstarted == jobs
    assert repo.scheduler_status()["jobs"][0]["last_execution"] is None

    def unavailable(_):
        raise RuntimeError("preflight failed")

    monkeypatch.setattr("excludarr.engine.build_radarr_items", unavailable)
    result = execute_batch(config, repo, "one", jobs, Event(), lambda: NOW)
    assert result.completed == {("rule", "A"): "failed"}
    assert result.unstarted == []


def test_library_only_daemon_waits_for_schedule(tmp_path):
    config, repo = setup(tmp_path)
    stopped = Event()
    running = Event()

    def clock():
        running.set()
        return NOW

    errors = []

    def run():
        try:
            run_daemon(config, repo, host="127.0.0.1", port=0, stop=stopped, now=clock)
        except Exception as error:  # noqa: BLE001 - surface failures from the test thread
            errors.append(error)

    thread = Thread(target=run)
    thread.start()
    try:
        assert running.wait(3)
    finally:
        stopped.set()
        thread.join(5)
    assert not thread.is_alive()
    assert errors == []
    assert repo.history() == []
    assert repo.scheduler_status()["daemon"]["stopped_at"] == NOW


def test_empty_daemon_is_rejected(tmp_path):
    config, repo = setup(tmp_path, rules=False)
    with pytest.raises(ConfigError):
        run_daemon(config, repo, host="127.0.0.1", port=0, stop=Event(), now=lambda: NOW)


@pytest.mark.parametrize("heartbeat_failure", [False, True])
def test_http_heartbeat_and_shutdown_while_worker_blocked(tmp_path, monkeypatch, heartbeat_failure):
    from http.client import HTTPConnection

    from excludarr import daemon
    from excludarr.list_config import ListProxyConfig
    from excludarr.lists.items import ListItem

    config, repo = setup(tmp_path)
    config.list_proxy = ListProxyConfig.model_validate(
        {
            "api_key": "test-key",
            "sources": {"s": {"type": "stevenlu"}},
            "lists": {
                "movies": {
                    "target": "radarr",
                    "sources": ["s"],
                    "schedule": "0 * * * *",
                    "when": {"year": {"min": 2000}},
                }
            },
        }
    )
    entered, release, heartbeat = Event(), Event(), Event()
    stop = Event()
    current, elapsed = [NOW], [0]
    captured, errors = [], []
    original_server = daemon.make_server

    def server(*args):
        value = original_server(*args)
        captured.append(value)
        return value

    original_heartbeat = repo.scheduler_heartbeat

    def beat(instance, at):
        heartbeat.set()
        if heartbeat_failure:
            from sqlalchemy.exc import SQLAlchemyError

            raise SQLAlchemyError("heartbeat storage unavailable")
        original_heartbeat(instance, at)

    def source(*args, **kwargs):
        entered.set()
        assert release.wait(8)
        return [ListItem("Old movie", "movie", year=1990, imdb_id="tt1")]

    monkeypatch.setattr(daemon, "make_server", server)
    monkeypatch.setattr(daemon, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(repo, "scheduler_heartbeat", beat)
    monkeypatch.setattr("excludarr.clients.list_sources.fetch_source", source)

    def run():
        try:
            run_daemon(config, repo, host="127.0.0.1", port=0, stop=stop, now=lambda: current[0])
        except Exception as error:  # noqa: BLE001 - report thread failures to the test
            errors.append(error)

    thread = Thread(target=run)
    thread.start()
    try:
        assert entered.wait(5)
        current[0] = NOW + timedelta(minutes=1)
        elapsed[0] = 6
        assert heartbeat.wait(5)
        conn = HTTPConnection(*captured[0].server_address, timeout=2)
        conn.request("GET", "/lists/movies?apikey=test-key")
        response = conn.getresponse()
        assert response.status == 503
        response.read()
        conn.close()
        stop.set()
        assert thread.is_alive()
    finally:
        release.set()
        stop.set()
        thread.join(8)
    assert not thread.is_alive()
    assert len(errors) == int(heartbeat_failure)
    assert captured[0].fileno() == -1
    assert repo.list_snapshot("movies").payload == [{"title": "Old movie", "imdb_id": "tt1"}]
    assert all(
        row["last_execution"] is None
        for row in repo.scheduler_status()["jobs"]
        if row["kind"] == "rule"
    )


@pytest.mark.parametrize(
    "ok,side_errors,outcome",
    [(False, [], "failed"), (True, ["side effect private-key failed"], "warning")],
)
def test_action_results_become_job_outcomes(tmp_path, monkeypatch, ok, side_errors, outcome):
    from excludarr.actions import ActionResult
    from excludarr.items import MediaItem

    config, repo = setup(tmp_path)
    config.rules[0].preview = False
    monkeypatch.setattr(Clients, "from_config", classmethod(lambda cls, c: cls()))
    monkeypatch.setattr(
        "excludarr.engine.build_radarr_items",
        lambda _: [MediaItem("radarr:movie:1", "movie", "Example", "Example", 1, year=2020)],
    )
    monkeypatch.setattr(
        "excludarr.engine.execute",
        lambda *a: ActionResult(
            ok, 0, "action private-key failed" if not ok else "done", side_errors
        ),
    )
    result = execute_batch(
        config, repo, "one", [PendingJob(("rule", "A"), NOW)], Event(), lambda: NOW
    )
    assert result.completed == {("rule", "A"): outcome}
    execution = repo.scheduler_status()["jobs"][0]["last_execution"]
    assert execution["error"]
    assert "private-key" not in execution["error"]
    assert "[redacted]" in execution["error"]


def test_leaving_soon_failure_is_a_sanitized_job_warning(tmp_path, monkeypatch, caplog):
    from excludarr.clients.plex import PlexItem
    from excludarr.config import PlexIntegration
    from excludarr.facts import Context
    from excludarr.items import MediaItem

    config, repo = setup(tmp_path)
    config.rules[0].preview = False
    config.rules[0].grace_period = timedelta(days=1)
    config.rules[0].leaving_soon_collection = True
    config.integrations.plex = PlexIntegration(url="http://plex", token="plex-private")

    class FailingPlex:
        def add_to_collection(self, *args):
            raise RuntimeError("plex-private private-key unavailable")

    monkeypatch.setattr(Clients, "from_config", classmethod(lambda cls, c: cls(plex=FailingPlex())))
    monkeypatch.setattr(
        "excludarr.engine.build_radarr_items",
        lambda _: [MediaItem("radarr:movie:1", "movie", "Example", "Example", 1, year=2020)],
    )
    monkeypatch.setattr(Context, "plex_item", lambda *a: PlexItem("1", "library", "movie"))
    result = execute_batch(
        config, repo, "one", [PendingJob(("rule", "A"), NOW)], Event(), lambda: NOW
    )
    assert result.completed == {("rule", "A"): "warning"}
    assert len(repo.queue_all()) == 1
    execution = repo.scheduler_status()["jobs"][0]["last_execution"]
    assert execution["summary"]["cleanup_warnings"] == 1
    assert "Leaving Soon" in execution["error"]
    assert "plex-private" not in execution["error"] + caplog.text
    assert "private-key" not in execution["error"] + caplog.text
