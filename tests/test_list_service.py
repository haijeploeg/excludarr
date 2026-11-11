from datetime import UTC, datetime

import pytest

from excludarr.clients.http import IntegrationError
from excludarr.config import Config
from excludarr.lists.service import refresh_list
from excludarr.storage.repo import Repo


def make_config(tmp_path, when=None):
    return Config.model_validate(
        {
            "database": f"sqlite:///{tmp_path}/db",
            "integrations": {"radarr": {"url": "http://r", "api_key": "arr-secret"}},
            "list_proxy": {
                "api_key": "feed-secret",
                "sources": {"s": {"type": "stevenlu"}},
                "lists": {
                    "movies": {
                        "target": "radarr",
                        "sources": ["s"],
                        "when": when or {"year": {"min": 2000}},
                    }
                },
            },
        }
    )


def test_exclude_unknown_preview_publish_and_failure(tmp_path, respx_mock):
    config = make_config(tmp_path)
    config.list_proxy.lists["movies"].on_unknown = "exclude"
    repo = Repo(config.database)
    route = respx_mock.get("https://s3.amazonaws.com/popular-movies/movies.json")
    route.respond(200, json=[{"title": "Example", "imdb_id": "tt0000001"}])
    now = datetime.now(UTC)
    report = refresh_list(config, "movies", repo, now, publish=False)
    assert report["summary"] == {"included": 0, "excluded": 1}
    assert repo.list_snapshot("movies") is None
    refresh_list(config, "movies", repo, now)
    assert repo.list_snapshot("movies").payload == []
    route.respond(401, json={"token": "source-secret"})
    with pytest.raises(IntegrationError):
        refresh_list(config, "movies", repo, now)
    snapshot = repo.list_snapshot("movies")
    assert snapshot.successful_at == now
    assert snapshot.last_error
    assert "secret" not in snapshot.last_error


def test_enrichment_dedup_and_empty_list(tmp_path, respx_mock):
    config = make_config(tmp_path)
    config.list_proxy.tmdb_token = __import__("pydantic").SecretStr("read-secret")
    repo = Repo(config.database)
    route = respx_mock.get("https://s3.amazonaws.com/popular-movies/movies.json")
    route.respond(200, json=[{"title": "Example", "imdb_id": "tt0000001"}] * 2)
    respx_mock.get("https://api.themoviedb.org/3/find/tt0000001").respond(
        200, json={"movie_results": [{"id": 1}]}
    )
    respx_mock.get("https://api.themoviedb.org/3/movie/1").respond(
        200, json={"id": 1, "release_date": "1990-01-01", "external_ids": {"imdb_id": "tt0000001"}}
    )
    report = refresh_list(config, "movies", repo, datetime.now(UTC))
    assert report["payload"] == [{"title": "Example", "imdb_id": "tt0000001"}]
    assert len(report["items"]) == 1
    route.respond(200, json=[])
    refresh_list(config, "movies", repo, datetime.now(UTC))
    assert repo.list_snapshot("movies").payload == []


def test_tvdb_only_streaming_is_enriched(tmp_path, respx_mock):
    import json

    import httpx

    from excludarr.list_config import ListProxyConfig

    config = make_config(tmp_path)
    config.profile.providers = ["Netflix"]
    config.list_proxy = ListProxyConfig.model_validate(
        {
            "api_key": "key",
            "tmdb_token": "read-secret",
            "sources": {"plex": {"type": "plex_watchlist", "token": "plex-secret"}},
            "lists": {
                "shows": {
                    "target": "sonarr",
                    "sources": ["plex"],
                    "when": {"streaming": "my_providers"},
                }
            },
        }
    )
    repo = Repo(config.database)
    respx_mock.get("https://discover.provider.plex.tv/library/sections/watchlist/all").respond(
        200,
        json={
            "MediaContainer": {
                "totalSize": 1,
                "Metadata": [{"title": "Show", "type": "show", "Guid": [{"id": "tvdb://42"}]}],
            }
        },
    )
    respx_mock.get("https://api.themoviedb.org/3/find/42").respond(
        200, json={"tv_results": [{"id": 1}]}
    )
    respx_mock.get("https://api.themoviedb.org/3/tv/1").respond(
        200, json={"id": 1, "external_ids": {"tvdb_id": 42}}
    )

    def gql(request):
        op = json.loads(request.content)["operationName"]
        if op == "GetSearchTitles":
            data = {
                "popularTitles": {
                    "edges": [
                        {
                            "node": {
                                "id": "show1",
                                "content": {
                                    "title": "Show",
                                    "externalIds": {"tmdbId": "1", "imdbId": None},
                                    "originalReleaseYear": 2025,
                                },
                            }
                        }
                    ]
                }
            }
        elif op == "GetPackages":
            data = {
                "packages": [
                    {
                        "packageId": 8,
                        "clearName": "Netflix",
                        "shortName": "nfx",
                        "monetizationTypes": ["FLATRATE"],
                    }
                ]
            }
        else:
            data = {
                "node": {
                    "seasons": [
                        {
                            "episodes": [
                                {"content": {"seasonNumber": 1, "episodeNumber": 1}, "offers": []}
                            ]
                        }
                    ]
                }
            }
        return httpx.Response(200, json={"data": data})

    respx_mock.post("https://apis.justwatch.com/graphql").mock(side_effect=gql)
    report = refresh_list(config, "shows", repo, datetime.now(UTC))
    assert report["payload"] == [{"title": "Show", "tvdbId": 42}]
    assert report["summary"]["excluded"] == 0


def test_later_page_http_failure_preserves_publication(tmp_path, respx_mock, monkeypatch):
    from datetime import timedelta

    from excludarr.list_config import ListProxyConfig

    monkeypatch.setattr("excludarr.clients.http._sleep", lambda _: None)
    config = make_config(tmp_path)
    config.list_proxy = ListProxyConfig.model_validate(
        {
            "api_key": "key",
            "tmdb_token": "secret",
            "sources": {"s": {"type": "tmdb", "mode": "list", "list_id": 42}},
            "lists": {
                "movies": {"target": "radarr", "sources": ["s"], "when": {"year": {"min": 2000}}}
            },
        }
    )
    repo = Repo(config.database)
    previous = datetime.now(UTC) - timedelta(hours=1)
    repo.list_publish("movies", [{"title": "Old", "imdb_id": "tt1"}], {}, "old", previous)
    respx_mock.get("https://api.themoviedb.org/4/list/42", params={"page": 1}).respond(
        200,
        json={
            "page": 1,
            "total_pages": 2,
            "results": [{"title": "New", "media_type": "movie", "id": 1}],
        },
    )
    respx_mock.get("https://api.themoviedb.org/4/list/42", params={"page": 2}).respond(500)
    attempted = datetime.now(UTC)
    with pytest.raises(IntegrationError):
        refresh_list(config, "movies", repo, attempted)
    snapshot = repo.list_snapshot("movies")
    assert snapshot.payload == [{"title": "Old", "imdb_id": "tt1"}]
    assert snapshot.successful_at == previous
    assert snapshot.last_attempt_at == attempted
    assert snapshot.fingerprint == "old"


@pytest.mark.parametrize(
    "identities",
    [
        [("tt1", 1), ("tt1", 2)],
        [("tt1", 1), ("tt2", 2), ("tt1", 2)],
    ],
)
def test_cross_source_identity_conflicts_abort(tmp_path, respx_mock, identities):
    from excludarr.list_config import ListProxyConfig

    config = make_config(tmp_path)
    sources = {
        f"s{i}": {
            "type": "trakt",
            "mode": "list",
            "user": "me",
            "list_id": f"list{i}",
            "client_id": "id",
        }
        for i in range(len(identities))
    }
    config.list_proxy = ListProxyConfig.model_validate(
        {
            "api_key": "key",
            "sources": sources,
            "lists": {
                "movies": {
                    "target": "radarr",
                    "sources": list(sources),
                    "when": {"year": {"min": 2000}},
                }
            },
        }
    )
    for i, (imdb, tmdb) in enumerate(identities):
        respx_mock.get(f"https://api.trakt.tv/users/me/lists/list{i}/items").respond(
            200,
            json=[
                {
                    "type": "movie",
                    "movie": {
                        "title": "Example",
                        "year": 1990,
                        "ids": {"imdb": imdb, "tmdb": tmdb},
                    },
                }
            ],
        )
    repo = Repo(config.database)
    with pytest.raises(IntegrationError):
        refresh_list(config, "movies", repo, datetime.now(UTC))
    assert repo.list_snapshot("movies").successful_at is None


def test_unknown_is_published_by_default(tmp_path, respx_mock):
    config = make_config(tmp_path)
    repo = Repo(config.database)
    respx_mock.get("https://s3.amazonaws.com/popular-movies/movies.json").respond(
        200, json=[{"title": "Example", "imdb_id": "tt0000001"}]
    )
    report = refresh_list(config, "movies", repo, datetime.now(UTC))
    assert report["payload"] == [{"title": "Example", "imdb_id": "tt0000001"}]
    assert report["items"][0]["unknown"] is True
    assert report["summary"] == {"included": 1, "excluded": 0}


@pytest.mark.parametrize(
    "target,kind,media,path,title_field,id_field",
    [
        ("sonarr", "series", "series", "tv", "name", "tvdb_id"),
        ("radarr", "movie", "movie", "movie", "title", "imdb_id"),
    ],
)
def test_missing_export_id_excludes_only_that_title(
    tmp_path, respx_mock, target, kind, media, path, title_field, id_field
):
    from excludarr.list_config import ListProxyConfig

    config = make_config(tmp_path)
    config.list_proxy = ListProxyConfig.model_validate(
        {
            "api_key": "feed-secret",
            "tmdb_token": "read-secret",
            "sources": {"popular": {"type": "tmdb", "mode": "popular", "media_type": media}},
            "lists": {
                "titles": {
                    "target": target,
                    "sources": ["popular"],
                    "when": {"year": {"min": 2000}},
                }
            },
        }
    )
    respx_mock.get(f"https://api.themoviedb.org/3/{path}/popular").respond(
        200,
        json={
            "page": 1,
            "total_pages": 1,
            "results": [
                {"id": 123, title_field: "Missing ID"},
                {"id": 124, title_field: "Valid title"},
            ],
        },
    )
    for ident, external in [(123, None), (124, 42 if target == "sonarr" else "tt42")]:
        respx_mock.get(f"https://api.themoviedb.org/3/{path}/{ident}").respond(
            200,
            json={
                "id": ident,
                "first_air_date": "1990-01-01",
                "release_date": "1990-01-01",
                "external_ids": {id_field: external},
            },
        )
    repo = Repo(config.database)
    report = refresh_list(config, "titles", repo, datetime.now(UTC))
    assert report["summary"] == {"included": 1, "excluded": 1}
    assert report["items"][0]["decision"] == "excluded"
    assert id_field in report["items"][0]["reason"]
    assert report["items"][0]["unknown"] is False
    expected = [
        {
            "title": "Valid title",
            "tvdbId" if target == "sonarr" else "imdb_id": 42 if target == "sonarr" else "tt42",
        }
    ]
    assert report["payload"] == expected
    assert repo.list_snapshot("titles").payload == expected
    assert repo.list_snapshot("titles").last_error is None


def test_diagnostic_redacts_credentials_in_item_context(tmp_path, respx_mock):
    from excludarr.list_config import ListProxyConfig

    config = make_config(tmp_path)
    config.list_proxy = ListProxyConfig.model_validate(
        {
            "api_key": "feed-secret",
            "tmdb_token": "read-secret",
            "sources": {"s": {"type": "tmdb", "mode": "popular", "media_type": "series"}},
            "lists": {
                "series": {"target": "sonarr", "sources": ["s"], "when": {"year": {"min": 2000}}}
            },
        }
    )
    respx_mock.get("https://api.themoviedb.org/3/tv/popular").respond(
        200,
        json={
            "page": 1,
            "total_pages": 1,
            "results": [{"id": 123, "name": "feed-secret read-secret"}],
        },
    )
    respx_mock.get("https://api.themoviedb.org/3/tv/123").respond(
        200, json={"id": 124, "external_ids": {"tvdb_id": None}}
    )
    with pytest.raises(IntegrationError) as caught:
        refresh_list(config, "series", Repo(config.database), datetime.now(UTC))
    assert "feed-secret" not in str(caught.value)
    assert "read-secret" not in str(caught.value)
    assert "[redacted]" in str(caught.value)
