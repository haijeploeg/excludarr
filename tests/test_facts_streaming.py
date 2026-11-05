from datetime import UTC, datetime

import httpx
import pytest
import respx

from excludarr.clients.justwatch import JustWatchClient
from excludarr.config import Config, ConfigError
from excludarr.facts import Clients, Context
from excludarr.items import EpisodeRef, MediaItem
from excludarr.storage.repo import Repo

GQL = "https://apis.justwatch.com/graphql"
NFX = frozenset({(8, "FLATRATE")})


@pytest.fixture
def ctx(tmp_path, minimal_cfg):
    cfg = Config.model_validate(minimal_cfg)
    clients = Clients(justwatch=JustWatchClient("en_US"))
    return Context(cfg, clients, Repo(f"sqlite:///{tmp_path / 'db.sqlite'}"), datetime.now(UTC))


def search_resp(node_id="tm1", tmdb="10"):
    edge = {
        "node": {
            "id": node_id,
            "content": {
                "title": "X",
                "originalReleaseYear": 2000,
                "externalIds": {"tmdbId": tmdb, "imdbId": None},
            },
        }
    }
    return {"data": {"popularTitles": {"edges": [edge]}}}


def mock_gql(search, node=None):
    def handler(request):
        import json

        op = json.loads(request.content)["operationName"]
        return httpx.Response(
            200, json=search if op == "GetSearchTitles" else {"data": {"node": node}}
        )

    return respx.post(GQL).mock(side_effect=handler)


def movie():
    return MediaItem("radarr:movie:1", "movie", "X (2000)", "X", 1, tmdb_id=10)


def ep(s, n, aired=True):
    return EpisodeRef(s * 100 + n, s, n, aired, None, 0, True)


def show(kind="season", season=1, eps=()):
    return MediaItem("k", kind, "S", "S", 1, season=season, tmdb_id=10, episodes=tuple(eps))


def show_node():
    def e(s, n, offers):
        return {"content": {"seasonNumber": s, "episodeNumber": n}, "offers": offers}

    off = [{"monetizationType": "FLATRATE", "package": {"packageId": 8}}]
    return {"seasons": [{"episodes": [e(1, 1, off), e(1, 2, off)]}]}


@respx.mock
def test_streaming_movie_unmatched_is_none(ctx):
    mock_gql(search_resp(tmdb="99"))
    assert ctx.streaming(movie()) is None


@respx.mock
def test_streaming_season_has_one_avail_per_aired_episode(ctx):
    mock_gql(search_resp(), show_node())
    item = show(eps=[ep(1, 1), ep(1, 2), ep(1, 3, aired=False), ep(2, 1)])
    assert ctx.streaming(item) == [NFX, NFX]


@respx.mock
def test_streaming_missing_season_is_empty_sets_not_none(ctx):
    mock_gql(search_resp(), show_node())
    item = show(season=3, eps=[ep(3, 1), ep(3, 2)])
    assert ctx.streaming(item) == [frozenset(), frozenset()]


@respx.mock
def test_streaming_lookup_failure_is_none(ctx):
    respx.post(GQL).mock(return_value=httpx.Response(200, json={"errors": [{"message": "x"}]}))
    assert ctx.streaming(movie()) is None


@respx.mock
def test_match_cached(ctx):
    route = mock_gql(search_resp(), {"offers": []})
    assert ctx.streaming(movie()) == [frozenset()]
    n = route.call_count
    assert ctx.streaming(movie()) == [frozenset()]
    assert route.call_count == n


@respx.mock
def test_unknown_provider_name_raises(ctx):
    pk = {"packageId": 8, "clearName": "Netflix", "shortName": "nfx", "monetizationTypes": []}
    route = respx.post(GQL).mock(
        return_value=httpx.Response(200, json={"data": {"packages": [pk]}})
    )
    assert ctx.provider_ids(["netflix"]) == {8}
    with pytest.raises(ConfigError, match="unknown provider 'Nope' for locale en_US"):
        ctx.provider_ids(["Nope"])
    assert route.call_count == 1  # providers cached


@respx.mock
def test_streaming_null_node_is_none_and_prefetch_does_not_raise(ctx):
    mock_gql(search_resp(), None)
    assert ctx.streaming(movie()) is None
    ctx.prefetch_streaming([movie()])


@respx.mock
def test_streaming_malformed_search_is_none(ctx):
    mock_gql({"data": {"popularTitles": {"edges": [{"node": {"id": "a", "content": None}}]}}})
    assert ctx.streaming(movie()) is None


@respx.mock
def test_streaming_series_spans_seasons_excluding_specials(ctx):
    mock_gql(search_resp(), show_node())
    item = show(kind="series", season=None, eps=[ep(0, 1), ep(1, 1), ep(1, 2), ep(2, 1)])
    assert ctx.streaming(item) == [NFX, NFX, frozenset()]


@respx.mock
def test_streaming_episode_is_single_unit(ctx):
    mock_gql(search_resp(), show_node())
    item = show(kind="episode", season=1)
    item.episode = 2
    assert ctx.streaming(item) == [NFX]


@respx.mock
def test_streaming_missing_episode_in_present_season_is_empty(ctx):
    mock_gql(search_resp(), show_node())
    item = show(eps=[ep(1, 1), ep(1, 5)])
    assert ctx.streaming(item) == [NFX, frozenset()]


@respx.mock
def test_unmatched_cached_as_empty_string(ctx):
    route = mock_gql(search_resp(tmdb="99"))
    assert ctx.streaming(movie()) is None
    n = route.call_count
    assert ctx.streaming(movie()) is None
    assert route.call_count == n


def test_streaming_memoized_per_item_including_none(ctx):
    calls = []
    ctx._match = lambda item, kind: calls.append(item.key)  # returns None: unknown
    assert ctx.streaming(movie()) is None
    assert ctx.streaming(movie()) is None
    assert calls == ["radarr:movie:1"]


@pytest.mark.parametrize(
    "failure",
    [httpx.ConnectError("down"), httpx.Response(500, text="oops")],
    ids=["transport", "5xx"],
)
@respx.mock
def test_justwatch_circuit_breaker(ctx, monkeypatch, caplog, failure):
    import logging

    monkeypatch.setattr("excludarr.clients.http._sleep", lambda s: None)
    route = respx.post(GQL)
    if isinstance(failure, Exception):
        route.mock(side_effect=failure)
    else:
        route.mock(return_value=failure)
    other = MediaItem("radarr:movie:2", "movie", "Y (2001)", "Y", 2, tmdb_id=20)
    with caplog.at_level(logging.WARNING):
        assert ctx.streaming(movie()) is None
        n = route.call_count
        assert ctx.streaming(other) is None
    assert route.call_count == n  # no HTTP after the breaker tripped
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1


@respx.mock
def test_graphql_error_does_not_trip_breaker(ctx):
    route = respx.post(GQL).mock(
        return_value=httpx.Response(200, json={"errors": [{"message": "x"}]})
    )
    assert ctx.streaming(movie()) is None
    n = route.call_count
    other = MediaItem("radarr:movie:2", "movie", "Y (2001)", "Y", 2, tmdb_id=20)
    assert ctx.streaming(other) is None
    assert route.call_count > n
