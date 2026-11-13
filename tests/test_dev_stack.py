from pathlib import Path

import httpx
import pytest

from dev import stack


def test_request_refuses_absolute_paths_and_redirects(respx_mock):
    with pytest.raises(stack.SetupError):
        stack.request("radarr", "GET", "http://personal-server/api/v3/movie")
    respx_mock.get("http://radarr:7878/api/v3/movie").respond(
        302, headers={"Location": "http://personal-server/api/v3/movie"}
    )
    with pytest.raises(stack.SetupError, match="redirect"):
        stack.request("radarr", "GET", "/api/v3/movie")


def test_request_errors_never_include_body_or_credentials(respx_mock, monkeypatch):
    monkeypatch.setattr(stack, "credentials", lambda: {"radarr": "private-token"})
    respx_mock.get("http://radarr:7878/api/v3/movie").respond(401, text="bad private-token")
    with pytest.raises(stack.SetupError) as error:
        stack.request("radarr", "GET", "/api/v3/movie")
    assert "private-token" not in str(error.value)
    assert "401" in str(error.value)


def test_wait_ready_has_deadline(respx_mock):
    respx_mock.get("http://radarr:7878/ping").mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(stack.SetupError, match="radarr"):
        stack.wait_ready("radarr", timeout=0)


def test_marker_refuses_foreign_volume(tmp_path):
    (tmp_path / "identity.json").write_text('{"project": "personal"}')
    with pytest.raises(stack.SetupError, match="identity"):
        stack.identity(tmp_path)


def test_marker_is_stable_and_private(tmp_path):
    first = stack.identity(tmp_path)
    assert first["project"] == "excludarr-dev"
    assert stack.identity(tmp_path) == first
    assert Path(tmp_path / "identity.json").stat().st_mode & 0o077 == 0


def test_manifest_rejects_unsafe_paths():
    with pytest.raises(stack.SetupError, match="path"):
        stack.validate_manifest(
            {"version": 1, "movies": [{"role": "../escape", "id": 550}], "series": []}
        )


def test_seed_arr_reuses_existing_ids(respx_mock, monkeypatch, tmp_path):
    monkeypatch.setattr(stack, "MEDIA", tmp_path)
    movie = {
        "id": 7,
        "tmdbId": 550,
        "title": "Fight Club",
        "year": 1999,
        "path": str(tmp_path / "movies/delete"),
        "tags": [3],
        "monitored": True,
    }
    respx_mock.get("http://radarr:7878/api/v3/movie").respond(200, json=[movie])
    respx_mock.get("http://radarr:7878/api/v3/tag").respond(
        200, json=[{"id": 3, "label": "dev-delete"}]
    )
    respx_mock.put("http://radarr:7878/api/v3/movie/7").respond(202, json=movie)
    respx_mock.get("http://radarr:7878/api/v3/exclusions").respond(200, json=[])
    fixture = {"role": "delete", "id": 550, "file": False}
    first = stack.ensure_arr_item("radarr", fixture)
    second = stack.ensure_arr_item("radarr", fixture)
    assert first["id"] == second["id"] == 7
    assert first["external_id"] == 550


def test_seed_arr_repairs_deleted_fixture(respx_mock, monkeypatch, tmp_path):
    monkeypatch.setattr(stack, "MEDIA", tmp_path)
    respx_mock.get("http://radarr:7878/api/v3/movie").respond(200, json=[])
    respx_mock.get("http://radarr:7878/api/v3/tag").respond(
        200, json=[{"id": 3, "label": "dev-delete"}]
    )
    respx_mock.get("http://radarr:7878/api/v3/exclusions").respond(
        200, json=[{"id": 9, "tmdbId": 550}, {"id": 10, "tmdbId": 603}]
    )
    removed = respx_mock.delete("http://radarr:7878/api/v3/exclusions/9").respond(200)
    respx_mock.get("http://radarr:7878/api/v3/movie/lookup", params={"term": "tmdb:550"}).respond(
        200, json=[{"title": "Fight Club", "tmdbId": 550, "year": 1999}]
    )
    respx_mock.get("http://radarr:7878/api/v3/qualityprofile").respond(200, json=[{"id": 12}])
    respx_mock.get("http://radarr:7878/api/v3/rootfolder").respond(200, json=[])
    respx_mock.post("http://radarr:7878/api/v3/rootfolder").respond(201, json={"id": 4})
    respx_mock.post("http://radarr:7878/api/v3/movie").respond(
        201,
        json={
            "id": 8,
            "tmdbId": 550,
            "title": "Fight Club",
            "year": 1999,
            "path": str(tmp_path / "movies/delete"),
            "tags": [3],
        },
    )
    restored = stack.ensure_arr_item("radarr", {"role": "delete", "id": 550, "file": False})
    assert restored["id"] == 8
    assert removed.called


def test_bootstrap_sonarr_names_only_empty_marked_instance(respx_mock, monkeypatch, tmp_path):
    monkeypatch.setattr(stack, "CONFIG", tmp_path)
    monkeypatch.setattr(stack, "VOLUMES", tmp_path / "services")
    respx_mock.get("http://sonarr:8989/ping").respond(200, json={"status": "OK"})
    marker = stack.identity(tmp_path)
    stack.save(tmp_path / "services/sonarr/.excludarr-dev.json", marker)
    respx_mock.get("http://sonarr:8989/api/v3/system/status").respond(
        200, json={"instanceName": "Sonarr"}
    )
    respx_mock.get("http://sonarr:8989/api/v3/series").respond(200, json=[{"id": 4}])
    with pytest.raises(stack.SetupError, match="nonempty"):
        stack.prepare_arr("sonarr")


def test_full_setup_requires_local_auth_without_leaking_token(monkeypatch, tmp_path):
    monkeypatch.setattr(stack, "VOLUMES", tmp_path)
    monkeypatch.setattr(stack, "CONFIG", tmp_path / "config")
    with pytest.raises(stack.SetupError, match="Plex"):
        stack.refresh_credentials()


def test_seed_failure_retains_completed_steps(monkeypatch, tmp_path):
    monkeypatch.setattr(stack, "CONFIG", tmp_path)
    monkeypatch.setattr(stack, "verify_stack", lambda **kwargs: {})
    monkeypatch.setattr(stack, "wait_ready", lambda *args: None)

    def ensure(service, fixture):
        if fixture["id"] == 603:
            raise stack.SetupError("metadata unavailable")
        return {"id": 7, "external_id": 550}

    monkeypatch.setattr(stack, "ensure_arr_item", ensure)
    with pytest.raises(stack.SetupError, match="metadata"):
        stack.seed_arr(
            {
                "version": 1,
                "movies": [{"role": "delete", "id": 550}, {"role": "files", "id": 603}],
                "series": [],
            }
        )
    import json

    assert json.loads((tmp_path / "state.json").read_text())["movies"]["delete"]["id"] == 7


def test_generated_configs_are_valid_and_preview_is_isolated(monkeypatch, tmp_path):
    import yaml

    from excludarr.config import load_config

    monkeypatch.setattr(stack, "credentials", lambda: {"radarr": "dev-a", "sonarr": "dev-b"})
    stack.write_configs({"movies": {}, "series": {}}, tmp_path, full=False)
    preview = load_config(tmp_path / "preview.yml")[0]
    actions = load_config(tmp_path / "actions.yml")[0]
    daemon = load_config(tmp_path / "daemon.yml")[0]
    assert all(rule.preview for rule in preview.rules)
    assert all(not rule.preview for rule in actions.rules)
    assert preview.database != actions.database == daemon.database

    for rule in actions.rules:
        assert "dev-" in yaml.safe_dump(
            yaml.safe_load((tmp_path / "actions.yml").read_text())["rules"][
                actions.rules.index(rule)
            ]["when"]
        )


def test_checks_refuse_wrong_identity_before_cli(monkeypatch):
    from dev.checks import run_checks

    def refuse(**kwargs):
        raise stack.SetupError("server identity mismatch")

    monkeypatch.setattr(stack, "verify_stack", refuse)
    with pytest.raises(stack.SetupError, match="identity"):
        run_checks(arr_only=True)


def test_module_entrypoint_uses_shared_module_identity(monkeypatch):
    import runpy

    called = []
    monkeypatch.setattr(stack, "main", lambda: called.append(True))
    runpy.run_path(stack.__file__, run_name="__main__")
    assert called == [True]


def test_reseed_clears_action_tags_and_existing_fixture_exclusion(
    respx_mock, monkeypatch, tmp_path
):
    monkeypatch.setattr(stack, "MEDIA", tmp_path)
    item = {
        "id": 7,
        "tmdbId": 550,
        "title": "Fight Club",
        "year": 1999,
        "path": str(tmp_path / "movies/delete"),
        "tags": [3, 5],
        "monitored": False,
    }
    respx_mock.get("http://radarr:7878/api/v3/movie").respond(200, json=[item])
    respx_mock.get("http://radarr:7878/api/v3/tag").respond(
        200, json=[{"id": 3, "label": "dev-delete"}]
    )
    respx_mock.get("http://radarr:7878/api/v3/exclusions").respond(
        200, json=[{"id": 9, "tmdbId": 550}]
    )
    removed = respx_mock.delete("http://radarr:7878/api/v3/exclusions/9").respond(200)
    updated = respx_mock.put("http://radarr:7878/api/v3/movie/7").respond(200, json=item)
    stack.ensure_arr_item("radarr", {"role": "delete", "id": 550, "file": False})
    import json

    assert json.loads(updated.calls[0].request.content)["tags"] == [3]
    assert removed.called


def test_initialize_recovers_existing_marked_api_keys_after_interruption(monkeypatch, tmp_path):
    monkeypatch.setattr(stack, "CONFIG", tmp_path / "config")
    monkeypatch.setattr(stack, "VOLUMES", tmp_path / "services")
    monkeypatch.setattr(stack, "MEDIA", tmp_path / "media")
    monkeypatch.setattr(stack.os, "chown", lambda *args: None)
    marker = stack.identity()
    directory = tmp_path / "services/radarr"
    stack.save(directory / ".excludarr-dev.json", marker)
    (directory / "config.xml").write_text("<Config><ApiKey>existing-local-key</ApiKey></Config>")
    stack.initialize()
    assert stack.credentials()["radarr"] == "existing-local-key"


def test_plex_seed_uses_library_locations_not_filter_navigation(respx_mock, monkeypatch, tmp_path):
    from dev import companions

    monkeypatch.setattr(stack, "MEDIA", Path("/media"))
    monkeypatch.setattr(stack, "plex_credentials", lambda: {"username": "dev-viewer"})
    respx_mock.get("http://plex:32400/library/sections").respond(
        200,
        json={
            "MediaContainer": {
                "Directory": [
                    {
                        "key": "1",
                        "title": "Excludarr Dev Movies",
                        "Location": [{"path": "/media/movies"}],
                    },
                    {
                        "key": "2",
                        "title": "Excludarr Dev Series",
                        "Location": [{"path": "/media/tv"}],
                    },
                ]
            }
        },
    )
    for key in ("1", "2"):
        respx_mock.get(f"http://plex:32400/library/sections/{key}").respond(
            200, json={"MediaContainer": {"Directory": [{"key": "all", "title": "All"}]}}
        )
        respx_mock.get(f"http://plex:32400/library/sections/{key}/refresh").respond(200)
        respx_mock.get(f"http://plex:32400/library/sections/{key}/all").respond(
            200,
            json={
                "MediaContainer": {
                    "Metadata": [
                        {"ratingKey": "42", "title": "Toy Story", "Guid": [{"id": "tmdb://862"}]}
                    ]
                    if key == "1"
                    else []
                }
            },
        )
    state = {
        "movies": {"watched": {"role": "watched", "files": ["clip.mkv"], "external_id": 862}},
        "series": {},
    }
    result = companions.seed_plex(state)
    assert result["items"][0]["rating_key"] == "42"
    assert result["username"] == "dev-viewer"


def test_tv_fixture_writes_explicit_plex_match_hint(respx_mock, monkeypatch, tmp_path):
    monkeypatch.setattr(stack, "MEDIA", tmp_path)
    series = {
        "id": 7,
        "tvdbId": 81189,
        "title": "Breaking Bad",
        "year": 2008,
        "path": str(tmp_path / "tv/episodes"),
        "tags": [3],
        "seasons": [],
    }
    respx_mock.get("http://sonarr:8989/api/v3/series").respond(200, json=[series])
    respx_mock.get("http://sonarr:8989/api/v3/tag").respond(
        200, json=[{"id": 3, "label": "dev-episodes"}]
    )
    respx_mock.get("http://sonarr:8989/api/v3/importlistexclusion").respond(200, json=[])
    respx_mock.put("http://sonarr:8989/api/v3/series/7").respond(200, json=series)
    stack.ensure_arr_item("sonarr", {"role": "episodes", "id": 81189, "file": False})
    assert (tmp_path / "tv/episodes/.plexmatch").read_text() == "tvdbid: 81189\n"


def test_plex_credentials_use_network_identity_not_raw_machine_id(monkeypatch, tmp_path):
    monkeypatch.setattr(stack, "CONFIG", tmp_path / "config")
    monkeypatch.setattr(stack, "VOLUMES", tmp_path / "services")
    path = tmp_path / "services/plex/Library/Preferences.xml"
    path.parent.mkdir(parents=True)
    path.write_text(
        '<Preferences MachineIdentifier="raw-local-id" ProcessedMachineIdentifier="network-id" PlexOnlineToken="test-only-token" PlexOnlineUsername="test-viewer"/>'
    )
    account = stack.plex_credentials()
    assert account["machine_id"] == "network-id"
    assert stack.credentials()["plex"] == "test-only-token"


def test_dev_preview_includes_live_streaming_without_enabling_actions(monkeypatch, tmp_path):
    import yaml

    from excludarr.config import load_config

    monkeypatch.setattr(stack, "credentials", lambda: {"radarr": "dev-a", "sonarr": "dev-b"})
    stack.write_configs({"movies": {}, "series": {}}, tmp_path, full=False)
    preview = yaml.safe_load((tmp_path / "preview.yml").read_text())
    assert preview["profile"] == {"locale": "nl_NL", "providers": ["Netflix"]}
    assert [rule["name"] for rule in preview["rules"][:2]] == [
        "streaming-movies",
        "streaming-series",
    ]
    streaming = {
        rule["name"]: rule for rule in preview["rules"] if rule["name"].startswith("streaming-")
    }
    assert set(streaming) == {"streaming-movies", "streaming-series"}
    assert streaming["streaming-movies"]["target"] == "radarr"
    assert streaming["streaming-series"]["level"] == "series"
    for rule in streaming.values():
        assert rule["preview"] is True
        assert rule["action"] == "delete_files"
        assert {"streaming": "my_providers"} in rule["when"]["all"]
        assert {"tag": "dev-protected"} in rule["unless"]
    for name in ("actions", "daemon", "fixture-preview"):
        config = load_config(tmp_path / f"{name}.yml")[0]
        assert not any(rule.name.startswith("streaming-") for rule in config.rules)
    fixtures = load_config(tmp_path / "fixture-preview.yml")[0]
    assert all(rule.preview for rule in fixtures.rules)
    assert fixtures.database != load_config(tmp_path / "preview.yml")[0].database
