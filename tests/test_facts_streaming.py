import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from excludarr.clients.justwatch import JustWatchClient
from excludarr.config import Config, ConfigError
from excludarr.facts import Clients, Context
from excludarr.items import EpisodeRef, MediaItem
from excludarr.storage.repo import Repo

GQL = "https://apis.justwatch.com/graphql"
NFX = frozenset({(8, "FLATRATE", None)})


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
        op = json.loads(request.content)["operationName"]
        return httpx.Response(
            200, json=search if op == "GetSearchTitles" else {"data": {"node": node}}
        )

    return respx.post(GQL).mock(side_effect=handler)


def movie():
    return MediaItem("radarr:movie:1", "movie", "X (2000)", "X", 1, tmdb_id=10)


@respx.mock
def test_prefetch_reports_every_database_cache_hit(ctx):
    items = [replace(movie(), key=f"radarr:movie:{i}", tmdb_id=i) for i in range(1, 58)]
    for item in items:
        node = f"node-{item.tmdb_id}"
        ctx.repo.cache_set(f"jw:match:MOVIE:{item.tmdb_id}", node, timedelta(days=1))
        ctx.repo.cache_set(
            f"jw:offers:v2:{node}", [[0, 0, [[8, "FLATRATE", None]]]], timedelta(days=1)
        )
    events = []
    ctx.prefetch_streaming(
        items, progress=lambda message, done, total: events.append((done, total))
    )
    assert events == [(done, 57) for done in range(58)]
    assert all(ctx.streaming(item) == [NFX] for item in items)
    assert not respx.calls


def ep(s, n, aired=True):
    return EpisodeRef(s * 100 + n, s, n, aired, None, 0, True)


def show(kind="season", season=1, eps=()):
    return MediaItem("k", kind, "S", "S", 1, season=season, tmdb_id=10, episodes=tuple(eps))


def show_node():
    def e(s, n, offers):
        return {"content": {"seasonNumber": s, "episodeNumber": n}, "offers": offers}

    off = [{"monetizationType": "FLATRATE", "package": {"packageId": 8}}]
    return {"seasons": [{"episodes": [e(1, 1, off), e(1, 2, off)]}]}


@pytest.mark.parametrize("kind", ["series", "season"])
@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        (["Netflix", "Amazon"], ["Amazon (rent) · 1/2 episodes", "Netflix"]),
        (["netflix"], ["Netflix"]),
        (["Amazon"], ["Amazon (rent) · 1/2 episodes"]),
        ([], []),
    ],
)
@respx.mock
def test_provider_labels_show_partial_episode_coverage_and_rental(ctx, kind, configured, expected):
    ctx.config.profile.providers = configured
    ctx.repo.cache_set("jw:match:SHOW:10", "show", timedelta(days=1))
    ctx.repo.cache_set(
        "jw:offers:v2:show",
        [
            [1, 1, [[8, "FLATRATE", None], [9, "RENT", None]]],
            [1, 2, [[8, "FLATRATE", None]]],
        ],
        timedelta(days=1),
    )
    ctx.repo.cache_set(
        "jw:providers:en_US",
        [
            {"id": 8, "clear_name": "Netflix", "short_name": "nfx", "monetization_types": []},
            {"id": 9, "clear_name": "Amazon", "short_name": "amz", "monetization_types": []},
        ],
        timedelta(days=1),
    )
    assert ctx.streaming_labels(show(kind=kind, eps=[ep(1, 1), ep(1, 2)])) == expected
    assert not respx.calls


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
    progress = []
    ctx.prefetch_streaming(
        [movie(), movie()], progress=lambda message, done, total: progress.append((done, total))
    )
    assert progress == [(0, 1), (1, 1)]


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
def test_unmatched_cached_as_empty_string(ctx, caplog):
    caplog.set_level("DEBUG", logger="excludarr.facts")
    route = mock_gql(search_resp(tmdb="99"))
    assert ctx.streaming(movie()) is None
    n = route.call_count
    next_run = Context(ctx.config, ctx.clients, ctx.repo, ctx.now)
    assert next_run.streaming(movie()) is None
    assert route.call_count == n
    assert "TMDB=10" in caplog.text and "tmdb_id=99" in caplog.text
    assert "Cache hit jw:match:v2:en_US:MOVIE:10" in caplog.text


@respx.mock
def test_search_fallback_retries_old_miss_and_keeps_local_offers(ctx):
    ctx.clients.justwatch = JustWatchClient("nl_NL")
    ctx.repo.cache_set("jw:match:MOVIE:10", "", timedelta(days=7))
    requests = []

    def handler(request):
        body = json.loads(request.content)
        operation, country = body["operationName"], body["variables"]["country"]
        requests.append((operation, country))
        if operation == "GetSearchTitles":
            data = search_resp(tmdb="10" if country == "US" else "99")
        else:
            data = {
                "data": {
                    "node": {
                        "offers": [
                            {"package": {"packageId": 8}, "monetizationType": "FLATRATE"},
                        ]
                    }
                }
            }
        return httpx.Response(200, json=data)

    respx.post(GQL).mock(side_effect=handler)
    assert ctx.streaming(movie()) == [NFX]
    assert requests == [
        ("GetSearchTitles", "NL"),
        ("GetSearchTitles", "US"),
        ("GetTitleOffers", "NL"),
    ]
    next_run = Context(ctx.config, ctx.clients, ctx.repo, ctx.now)
    assert next_run.streaming(movie()) == [NFX]
    assert len(requests) == 3


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


@pytest.mark.parametrize("failure", [False, True])
@respx.mock
def test_refresh_bypasses_existing_offers_and_reuses_fresh_lookup(ctx, failure):
    ctx.repo.cache_set("jw:match:v2:en_US:MOVIE:10", "tm1", timedelta(days=1))
    key = "jw:offers:v2:tm1"
    old = [[0, 0, [[8, "FLATRATE", None]]]]
    ctx.repo.cache_set(key, old, timedelta(days=1))
    route = mock_gql(search_resp(), None if failure else {"offers": []})
    fresh = Context(ctx.config, ctx.clients, ctx.repo, ctx.now, refresh=True)
    assert fresh.streaming(movie()) == (None if failure else [frozenset()])
    assert fresh.streaming(movie()) == (None if failure else [frozenset()])
    assert route.call_count == 2
    assert ctx.repo.cache_get(key) == (old if failure else [[0, 0, []]])


@respx.mock
def test_failed_lookup_preserves_already_refreshed_item(ctx, monkeypatch):
    monkeypatch.setattr("excludarr.clients.http._sleep", lambda s: None)
    route = mock_gql(
        search_resp(),
        {"offers": [{"monetizationType": "FLATRATE", "package": {"packageId": 8}}]},
    )
    fresh = Context(ctx.config, ctx.clients, ctx.repo, ctx.now, refresh=True)
    assert fresh.streaming(movie()) == [NFX]
    route.mock(return_value=httpx.Response(500))
    other = replace(movie(), key="radarr:movie:2", tmdb_id=20)
    assert fresh.streaming(other) is None
    assert fresh.streaming(movie()) == [NFX]


@respx.mock
def test_quality_cache_round_trip_and_legacy_refetch(ctx):
    ctx.repo.cache_set("jw:match:v2:en_US:MOVIE:10", "tm1", timedelta(days=1))
    ctx.repo.cache_set("jw:offers:tm1", [[0, 0, [[8, "FLATRATE"]]]], timedelta(days=1))
    node = {
        "offers": [
            {"package": {"packageId": 8}, "monetizationType": "FLATRATE", "presentationType": "HD"},
            {"package": {"packageId": 8}, "monetizationType": "FLATRATE"},
        ]
    }
    route = mock_gql(search_resp(), node)
    expected = [frozenset({(8, "FLATRATE", "hd"), (8, "FLATRATE", None)})]
    assert ctx.streaming(movie()) == expected
    assert route.call_count == 1
    fresh = Context(ctx.config, ctx.clients, ctx.repo, ctx.now)
    assert fresh.streaming(movie()) == expected
    assert route.call_count == 1


def test_quality_variants_do_not_inflate_provider_coverage(ctx, monkeypatch):
    from excludarr.clients.justwatch import Provider

    ctx.config.profile.providers = ["Netflix"]
    monkeypatch.setattr(
        ctx,
        "streaming",
        lambda item: [frozenset({(8, "FLATRATE", "sd"), (8, "FLATRATE", "hd")}), frozenset()],
    )
    monkeypatch.setattr(ctx, "_providers", lambda: [Provider(8, "Netflix", "nfx", ["FLATRATE"])])
    assert ctx.streaming_labels(movie()) == ["Netflix · 1/2 episodes"]
