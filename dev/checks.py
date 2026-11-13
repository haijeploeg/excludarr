"""Explicit destructive checks of generated fixture data only."""

import json
import signal
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import yaml

from dev import stack


def cli(config: str, *args: str, expected: int = 0) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["excludarr", "--config", str(stack.CONFIG / config), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != expected:
        raise stack.SetupError(
            f"CLI {args[0]}: exit {result.returncode}, expected {expected}; "
            "inspect the test services; command output withheld to protect credentials"
        )
    return result


def ensure(condition: bool, detail: str) -> None:
    if not condition:
        raise stack.SetupError(detail)


def snapshot() -> dict:
    result = {}
    for service, kind in [("radarr", "movie"), ("sonarr", "series")]:
        result[service] = {}
        for item in stack.request(service, "GET", "/api/v3/" + kind):
            row = {"monitored": item["monitored"], "tags": sorted(item["tags"])}
            if service == "radarr":
                row["files"] = [
                    f["id"]
                    for f in stack.request(
                        service, "GET", "/api/v3/moviefile", params={"movieId": item["id"]}
                    )
                ]
            else:
                row["seasons"] = [(s["seasonNumber"], s["monitored"]) for s in item["seasons"]]
                row["episodes"] = [
                    (e["id"], e["monitored"], e.get("episodeFileId"))
                    for e in stack.request(
                        service, "GET", "/api/v3/episode", params={"seriesId": item["id"]}
                    )
                ]
            result[service][str(item["id"])] = row
    return result


def daemon_check() -> None:
    """Start the actual daemon with an eight-second source request in progress."""
    config = yaml.safe_load((stack.CONFIG / "actions.yml").read_text())
    config["rules"] = [
        {
            "name": "daemon-tag",
            "target": "radarr",
            "action": "tag",
            "tag": "dev-scheduled",
            "preview": False,
            "when": {"tag": "dev-tag"},
            "schedule": "* * * * *",
        }
    ]
    config["database"] = f"sqlite:///{stack.CONFIG}/daemon-check.db"
    config["list_proxy"]["sources"]["fixture"]["url"] = "http://fixtures:8000/blocked.json"
    path = stack.CONFIG / "daemon-check.yml"
    path.write_text(yaml.safe_dump(config))
    path.chmod(0o600)
    # A dedicated throwaway DB forces bootstrap on every check; never touch action state.
    for suffix in ("", "-wal", "-shm"):
        (stack.CONFIG / ("daemon-check.db" + suffix)).unlink(missing_ok=True)
    child = subprocess.Popen(
        ["excludarr", "--config", str(path), "daemon", "--host", "127.0.0.1", "--port", "18991"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 6
        responsive = False
        locked = False
        while time.monotonic() < deadline:
            ensure(child.poll() is None, "Daemon exited before readiness")
            try:
                with httpx.Client(timeout=1, trust_env=False) as client:
                    status = client.get(
                        "http://127.0.0.1:18991/lists/movies",
                        params={"apikey": config["list_proxy"]["api_key"]},
                    ).status_code
                responsive = status == 503
                if responsive:
                    blocked = subprocess.run(
                        ["excludarr", "--config", str(path), "lists", "refresh", "movies"],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=3,
                    )
                    locked = (
                        blocked.returncode != 0
                        and "execution is active" in (blocked.stdout + blocked.stderr).lower()
                    )
                    if locked:
                        break
            except (httpx.HTTPError, subprocess.TimeoutExpired):
                pass
            time.sleep(0.1)
        ensure(
            responsive and locked, "HTTP or shared execution lock failed while source was blocked"
        )
        child.send_signal(signal.SIGTERM)
        ensure(child.wait(timeout=25) == 0, "Daemon did not drain and stop successfully")
        # A separate feed-only server tests auth and reads the published bootstrap snapshot.
        server = subprocess.Popen(
            ["excludarr", "--config", str(path), "serve", "--host", "127.0.0.1", "--port", "18991"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                try:
                    with httpx.Client(timeout=1, trust_env=False) as client:
                        good = client.get(
                            "http://127.0.0.1:18991/lists/movies",
                            params={"apikey": config["list_proxy"]["api_key"]},
                        )
                        bad = client.get(
                            "http://127.0.0.1:18991/lists/movies",
                            params={"apikey": "invalid-development-key"},
                        )
                    if good.status_code == 200:
                        ensure(bool(good.json()), "Published fixture list is unexpectedly empty")
                        ensure(bad.status_code == 401, "Invalid feed key was accepted")
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
            else:
                raise stack.SetupError("Feed snapshot was not published during daemon shutdown")
        finally:
            server.terminate()
            server.wait(timeout=10)
        status = cli("daemon-check.yml", "schedule", "status", "-o", "json")
        ensure("movies" in status.stdout, "Scheduler status did not report the fixture list")
        from excludarr.storage.repo import Repo

        repo = Repo(config["database"])
        previous = {
            job["name"]: (job["last_execution"] or {}).get("id", 0)
            for job in repo.scheduler_status()["jobs"]
        }
        scheduled = subprocess.Popen(
            [
                "excludarr",
                "--config",
                str(path),
                "daemon",
                "--host",
                "127.0.0.1",
                "--port",
                "18991",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 85
            while time.monotonic() < deadline:
                ensure(scheduled.poll() is None, "Scheduled daemon exited unexpectedly")
                jobs = repo.scheduler_status()["jobs"]
                if len(jobs) == 2 and all(
                    job["last_execution"]
                    and job["last_execution"]["id"] > previous.get(job["name"], 0)
                    and job["last_execution"]["outcome"] in ("success", "warning")
                    for job in jobs
                ):
                    break
                time.sleep(1)
            else:
                raise stack.SetupError(
                    "Cron did not complete both the fixture feed and library rule"
                )
            tags = {
                tag["id"]: tag["label"] for tag in stack.request("radarr", "GET", "/api/v3/tag")
            }
            movies = stack.request("radarr", "GET", "/api/v3/movie")
            subjects = [movie for movie in movies if "dev-tag" in [tags[t] for t in movie["tags"]]]
            ensure(
                len(subjects) == 1 and "dev-scheduled" in [tags[t] for t in subjects[0]["tags"]],
                "Scheduled library rule did not apply its tag",
            )
        finally:
            scheduled.terminate()
            try:
                scheduled.wait(timeout=25)
            except subprocess.TimeoutExpired:
                scheduled.kill()
                scheduled.wait()

    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=25)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


def run_checks(*, arr_only: bool = False) -> list[dict]:
    stack.verify_stack(full=not arr_only)
    state_path = stack.CONFIG / "state.json"
    ensure(state_path.exists(), "Seed this project before running checks")
    state = json.loads(state_path.read_text())
    ensure(state.get("identity") == stack.identity(), "Seed state identity mismatch")
    ensure(
        set(state["movies"])
        >= {"delete", "files", "monitor", "unmonitor", "tag", "grace", "protected"},
        "Seed is incomplete",
    )
    stack.write_configs(state, stack.CONFIG, full=not arr_only)
    # Refuse checks against a daemon using the shared state, before any action starts.
    from excludarr.locking import daemon_lock

    with daemon_lock(f"sqlite:///{stack.CONFIG}/actions.db"):
        pass
    results = []

    def check(name, operation):
        print(f"checking: {name}", flush=True)
        try:
            operation()
        except (
            stack.SetupError,
            subprocess.SubprocessError,
            OSError,
            ValueError,
            KeyError,
        ) as error:
            detail = str(error) if isinstance(error, stack.SetupError) else type(error).__name__
            results.append({"name": name, "status": "failed", "detail": detail})
            for result in results:
                print(f"{result['status']}: {result['name']} {result['detail']}", flush=True)
            print("skipped: remaining checks depend on the failed scenario", flush=True)
            # Stop after a failed destructive scenario; dependent checks would mislead.
            raise stack.SetupError(f"{name}: {detail}") from None
        results.append({"name": name, "status": "passed", "detail": ""})

    before = snapshot()
    protected = {
        service: before[service][str(state[group]["protected"]["id"])]
        for service, group in [("radarr", "movies"), ("sonarr", "series")]
    }

    def preview():
        cli("fixture-preview.yml", "run", "--yes")
        ensure(snapshot() == before, "Preview changed service state")
        ensure(
            all(
                Path(p).exists()
                for group in ("movies", "series")
                for item in state[group].values()
                for p in item["files"]
            ),
            "Preview removed media",
        )

    check("preview preserves API state and files", preview)

    def rule(name):
        cli("actions.yml", "run", "--yes", "--rule", name)

    def movie(role):
        return stack.request("radarr", "GET", f"/api/v3/movie/{state['movies'][role]['id']}")

    for name, wanted in [("monitor", True), ("unmonitor", False)]:

        def monitoring(name=name, wanted=wanted):
            rule(name)
            ensure(movie(name)["monitored"] is wanted, f"{name} state incorrect")

        check(name, monitoring)

    def tags():
        rule("tag")
        tags = {t["id"]: t["label"] for t in stack.request("radarr", "GET", "/api/v3/tag")}
        ensure("dev-checked" in [tags[t] for t in movie("tag")["tags"]], "Tag was not applied")

    check("tag", tags)

    def files():
        rule("files")
        ensure(not movie("files")["monitored"], "delete_files did not unmonitor")
        ensure(not movie("files")["hasFile"], "Arr still has the deleted movie file")
        ensure(
            not any(Path(p).exists() for p in state["movies"]["files"]["files"]),
            "Movie file survived deletion",
        )

    check("delete_files keeps movie and removes real clip", files)

    def deletion():
        rule("delete")
        all_movies = stack.request("radarr", "GET", "/api/v3/movie")
        ensure(
            not any(m["id"] == state["movies"]["delete"]["id"] for m in all_movies),
            "Movie entry survived",
        )
        ensure(
            not any(Path(p).exists() for p in state["movies"]["delete"]["files"]),
            "Deleted movie clip survived",
        )
        exclusions = stack.request("radarr", "GET", "/api/v3/exclusions")
        ensure(
            any(e["tmdbId"] == state["movies"]["delete"]["external_id"] for e in exclusions),
            "Missing import exclusion",
        )

    check("delete and import exclusion", deletion)

    def sonarr():
        sid = state["series"]["seasons"]["id"]
        for action, monitored in [("season-unmonitor", False), ("season-monitor", True)]:
            rule(action)
            data = stack.request("sonarr", "GET", f"/api/v3/series/{sid}")
            ensure(
                all(s["monitored"] is monitored for s in data["seasons"] if s["seasonNumber"] > 0),
                "Season monitor state incorrect",
            )
        rule("episode-files")
        ensure(
            not any(Path(p).exists() for p in state["series"]["episodes"]["files"]),
            "Episode clips survived",
        )
        ensure(
            not stack.request(
                "sonarr",
                "GET",
                "/api/v3/episodefile",
                params={"seriesId": state["series"]["episodes"]["id"]},
            ),
            "Episode files remain registered",
        )
        rule("series-exclusion")
        exclusions = stack.request("sonarr", "GET", "/api/v3/importlistexclusion")
        ensure(
            any(e["tvdbId"] == state["series"]["episodes"]["external_id"] for e in exclusions),
            "Missing Sonarr exclusion",
        )

    check("Sonarr season/episode actions and series exclusion", sonarr)

    def grace():
        from excludarr.config import load_config
        from excludarr.execution import execute_rules
        from excludarr.facts import Clients, Context
        from excludarr.storage.repo import Repo

        config, _ = load_config(stack.CONFIG / "actions.yml")
        repo = Repo(config.database)
        rule("grace")
        queued = repo.queue_for("grace")
        ensure(len(queued) == 1, "Grace queue must contain exactly one fixture")
        key = next(iter(queued))

        def member():
            fixture = state["movies"]["grace"]
            data = stack.request("plex", "GET", f"/library/metadata/{fixture['plex_key']}")
            return any(
                c["tag"] == "Excludarr Dev Leaving Soon"
                for m in data["MediaContainer"].get("Metadata", [])
                for c in m.get("Collection", [])
            )

        if not arr_only:
            ensure(member(), "Plex Leaving Soon membership missing")
        cli("actions.yml", "rescue", key, "--rule", "grace", "--once")
        ensure(not repo.queue_for("grace"), "Rescue did not clear the queue")
        if not arr_only:
            ensure(not member(), "Rescue did not remove Plex collection membership")
        rule("grace")
        clients = Clients.from_config(config)
        try:
            reports = execute_rules(
                Context(config, clients, repo, datetime.now(UTC) + timedelta(hours=2)),
                dry_run=False,
                rule_filter="grace",
            )
            ensure(
                not any(
                    not result.ok or result.side_effect_errors
                    for r in reports
                    for _, result in r.executed
                ),
                "Grace execution reported errors",
            )
        finally:
            clients.close()
        ensure(not repo.queue_for("grace"), "Expired grace entry survived")
        ensure(
            not any(Path(p).exists() for p in state["movies"]["grace"]["files"]),
            "Grace did not remove the clip",
        )
        if not arr_only:
            requests = stack.request(
                "seerr", "GET", "/api/v1/request", params={"take": 100, "filter": "all"}
            )["results"]
            ensure(
                not any(r["id"] == state["seerr"]["movies"]["request_id"] for r in requests),
                "Seerr request cleanup failed",
            )

    check("grace enqueue, rescue and expiry" + (" with Plex/Seerr" if not arr_only else ""), grace)

    if not arr_only:

        def history():
            for name in ("watched", "oldwatch"):
                rule(name)
                tags = {t["id"]: t["label"] for t in stack.request("radarr", "GET", "/api/v3/tag")}
                ensure(
                    "dev-history-ok" in [tags[t] for t in movie(name)["tags"]],
                    "Watch-history rule did not act",
                )

        check("Tautulli recent and old watch rules", history)
    else:
        results.append(
            {"name": "Plex/Tautulli/Seerr", "status": "skipped", "detail": "explicit --arr-only"}
        )
    check("daemon HTTP, locks, drain, feed auth, status and cron jobs", daemon_check)
    after = snapshot()
    ensure(
        all(
            after[service][str(state[group]["protected"]["id"])] == protected[service]
            for service, group in [("radarr", "movies"), ("sonarr", "series")]
        ),
        "Protected control changed",
    )
    results.append({"name": "protected controls", "status": "passed", "detail": ""})
    print("Checks complete. Reseed before repeating or starting the action daemon.", flush=True)
    return results
