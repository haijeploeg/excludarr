import json

import pytest
from typer.testing import CliRunner

from excludarr.cli import app


@pytest.mark.parametrize("exclude", [False, True])
def test_cli_reports_and_local_status(tmp_path, respx_mock, exclude):
    path = tmp_path / "config.yml"
    path.write_text("""integrations:
  radarr: {url: "http://r", api_key: arr-secret}
list_proxy:
  api_key: feed-secret
  sources:
    s: {type: stevenlu}
  lists:
    movies:
      target: radarr
      sources: [s]
      when: {year: {min: 2000}}
""")
    if exclude:
        path.write_text(
            path.read_text().replace(
                "      target: radarr", "      on_unknown: exclude\n      target: radarr"
            )
        )
    runner = CliRunner()
    prefix = ["--config", str(path), "lists"]
    respx_mock.get("https://s3.amazonaws.com/popular-movies/movies.json").respond(
        200, json=[{"title": "Example", "imdb_id": "tt0000001"}]
    )
    result = runner.invoke(app, prefix + ["refresh", "-o", "json"])
    assert result.exit_code == int(exclude), result.output
    doc = json.loads(result.stdout)
    assert doc["items"][0]["summary"]["excluded"] == int(exclude)
    assert "feed-secret" not in result.output
    status = runner.invoke(app, prefix + ["status", "-o", "json"])
    assert status.exit_code == 0, status.output
    assert json.loads(status.stdout)["items"][0]["excluded"] == int(exclude)
    preview = runner.invoke(app, prefix + ["preview", "missing", "-o", "json"])
    assert preview.exit_code == 1
    assert json.loads(preview.stdout)["status"] == "error"


def test_config_validate_includes_list_rules(tmp_path, respx_mock):
    path = tmp_path / "config.yml"
    path.write_text(
        'integrations:\n  radarr: {url: "http://r", api_key: key}\nlist_proxy:\n  api_key: feed-secret\n  sources:\n    s: {type: stevenlu}\n  lists:\n    movies:\n      target: radarr\n      sources: [s]\n      when: {streaming: {providers: [NotReal]}}\n'
    )
    respx_mock.post("https://apis.justwatch.com/graphql").respond(
        200,
        json={
            "data": {
                "packages": [
                    {
                        "packageId": 8,
                        "clearName": "Netflix",
                        "shortName": "nfx",
                        "monetizationTypes": ["FLATRATE"],
                    }
                ]
            }
        },
    )
    result = CliRunner().invoke(app, ["--config", str(path), "config", "validate", "-o", "json"])
    assert result.exit_code == 1
    assert "unknown provider" in json.loads(result.stdout)["errors"][0]

    path.write_text(path.read_text().replace("NotReal", "Netflix"))
    result = CliRunner().invoke(app, ["--config", str(path), "config", "validate", "-o", "json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["items"][0]["rule"] == "movies"


def test_preview_table_shows_observed_streaming_result(tmp_path, monkeypatch):
    path = tmp_path / "config.yml"
    path.write_text("""integrations:
  radarr: {url: "http://r", api_key: key}
list_proxy:
  api_key: feed-key
  sources:
    s: {type: stevenlu}
  lists:
    movies:
      target: radarr
      sources: [s]
      when: {year: {min: 2000}}
""")
    items = []
    for title, matched, decision in [
        ("Available", True, "excluded"),
        ("Unavailable", False, "included"),
    ]:
        items.append(
            {
                "title": title,
                "decision": decision,
                "evidence": [
                    {
                        "condition": "streaming",
                        "label": "on my providers (flatrate)",
                        "result": matched,
                        "observed": {
                            "matched_offers": [
                                {"provider_id": 8, "provider": "Netflix", "type": "FLATRATE"}
                            ]
                            if matched
                            else [],
                            "covered_units": int(matched),
                            "total_units": 1,
                        },
                    }
                ],
            }
        )
    items.append(
        {
            "title": "Missing ID",
            "decision": "excluded",
            "unknown": False,
            "reason": "Missing tvdb_id; cannot export to Sonarr",
            "evidence": [],
        }
    )
    items.append({"title": "Unknown", "decision": "excluded", "unknown": True, "evidence": []})
    items.append(
        {"title": "Allowed unknown", "decision": "included", "unknown": True, "evidence": []}
    )
    monkeypatch.setattr(
        "excludarr.lists.service.refresh_list",
        lambda *args, **kw: {
            "name": "movies",
            "summary": {"included": 2, "excluded": 2},
            "items": items,
            "payload": [],
        },
    )
    result = CliRunner().invoke(
        app, ["--config", str(path), "lists", "preview", "movies"], terminal_width=180
    )
    text = " ".join(result.stdout.split())
    assert "Missing ID excluded Missing tvdb_id; cannot export to Sonarr" in text
    assert "Held" not in text
    assert "Available excluded Netflix · subscription" in text
    assert "no qualifying offers" in text
    assert ": false" in text
    assert "Unknown excluded Required data unavailable; blocked by on_unknown: exclude" in text
    assert (
        "Allowed unknown included Required data unavailable; allowed by on_unknown: include" in text
    )


@pytest.mark.parametrize("snapshot_state", ["absent", "failed", "empty_report"])
def test_status_without_counts(tmp_path, snapshot_state, respx_mock):
    from datetime import UTC, datetime

    from excludarr.config import database_url, load_config
    from excludarr.storage.repo import Repo

    path = tmp_path / "config.yml"
    path.write_text("""integrations:
  radarr: {url: "http://r", api_key: key}
list_proxy:
  api_key: feed-key
  sources:
    s: {type: stevenlu}
  lists:
    movies:
      target: radarr
      sources: [s]
      when: {year: {min: 2000}}
""")
    config, _ = load_config(path)
    repo = Repo(database_url(config, path))
    if snapshot_state == "failed":
        repo.list_failure("movies", "Source unavailable", datetime.now(UTC))
    elif snapshot_state == "empty_report":
        repo.list_publish("movies", [], {}, "old", datetime.now(UTC))
    runner = CliRunner()
    command = ["--config", str(path), "lists", "status"]
    table = runner.invoke(app, command, terminal_width=180)
    assert table.exit_code == 0, table.output
    assert "movies" in table.stdout
    assert "—" in table.stdout
    structured = runner.invoke(app, command + ["-o", "json"])
    assert structured.exit_code == 0, structured.output
    row = json.loads(structured.stdout)["items"][0]
    assert row["included"] is None
    assert row["excluded"] is None


def test_serve_lists_endpoints_without_exposing_key(monkeypatch):
    from types import SimpleNamespace

    from excludarr.config import Config

    config = Config.model_validate(
        {
            "integrations": {"radarr": {"url": "http://r", "api_key": "arr-secret"}},
            "list_proxy": {
                "api_key": "feed-secret",
                "sources": {"s": {"type": "plex_watchlist", "token": "plex-secret"}},
                "lists": {
                    name: {"target": target, "sources": ["s"], "when": {"year": {"min": 2000}}}
                    for name, target in [("movies", "radarr"), ("series", "sonarr")]
                },
            },
        }
    )
    monkeypatch.setattr("excludarr.cli._list_config", lambda: (config, None))
    monkeypatch.setattr(
        "excludarr.lists.server.make_server",
        lambda *a: SimpleNamespace(serve_forever=lambda: None, server_close=lambda: None),
    )
    result = CliRunner().invoke(app, ["serve"], terminal_width=180)
    assert result.exit_code == 0, result.output
    text = " ".join(result.stderr.split())
    assert "movies Radarr http://127.0.0.1:8989/lists/movies" in text
    assert "series Sonarr http://127.0.0.1:8989/lists/series" in text
    assert "?apikey=<API_KEY>" in text
    assert "feed-secret" not in result.output
    assert "plex-secret" not in result.output
