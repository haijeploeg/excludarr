from pathlib import Path

from excludarr.config import load_config

EXAMPLE = Path(__file__).parent.parent / ".examples" / "excludarr-example.yml"


def test_example_config_validates(monkeypatch):
    for var in (
        "RADARR_API_KEY",
        "SONARR_API_KEY",
        "TAUTULLI_API_KEY",
        "SEERR_API_KEY",
        "PLEX_TOKEN",
    ):
        monkeypatch.setenv(var, "secret")
    cfg, _ = load_config(EXAMPLE)
    assert [(r.name, r.action, r.delete_files, r.import_exclusion) for r in cfg.rules] == [
        ("Streaming movies", "delete_files", False, False),
        ("Stale movies", "delete", True, True),
        ("Unwatched seasons", "delete_files", False, False),
        ("Trim old seasons", "unmonitor", False, False),
        ("Monitor again when it leaves streaming", "monitor", False, False),
        ("Tag big unrated movies", "tag", False, False),
    ]


def test_cron_sources_container_env():
    root = EXAMPLE.parent.parent
    jobs = [
        line
        for line in (root / ".examples" / "crontab").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert jobs and all(
        ". /etc/excludarr/env.sh && excludarr run -y > /proc/1/fd/1 2>&1" in j for j in jobs
    )
    assert "export -p > /etc/excludarr/env.sh" in (root / "entrypoint.sh").read_text()


def test_list_proxy_example(monkeypatch):
    from pathlib import Path

    from excludarr.config import load_config

    for key in (
        "RADARR_API_KEY",
        "SONARR_API_KEY",
        "LIST_PROXY_API_KEY",
        "TMDB_READ_TOKEN",
        "TRAKT_CLIENT_ID",
        "TRAKT_ACCESS_TOKEN",
        "PLEX_TOKEN",
    ):
        monkeypatch.setenv(key, "example-secret")
    config, _ = load_config(Path(".examples/list-proxy-example.yml"))
    assert set(config.list_proxy.lists) == {"movies", "series"}
    assert len(config.list_proxy.sources) == 9
