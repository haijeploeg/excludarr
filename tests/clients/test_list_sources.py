import httpx
import pytest

from excludarr.clients.http import IntegrationError
from excludarr.clients.list_sources import fetch_source
from excludarr.list_config import SourceConfig


@pytest.mark.respx(base_url="https://api.trakt.tv")
@pytest.mark.parametrize("mode", ["popular", "trending", "list", "watchlist"])
def test_trakt_modes(respx_mock, mode):
    kw = {"type": "trakt", "mode": mode, "client_id": "client-secret"}
    if mode in ("popular", "trending"):
        kw.update(media_type="movie")
        path = f"/movies/{mode}"
    elif mode == "list":
        kw.update(user="me", list_id="saved")
        path = "/users/me/lists/saved/items"
    else:
        kw.update(token="access-secret")
        path = "/sync/watchlist"
    item = {"title": "Example", "year": 2025, "ids": {"imdb": "tt0000001", "tmdb": 1}}
    body = [item] if mode == "popular" else [{"type": "movie", "movie": item}]
    respx_mock.get(path).mock(return_value=httpx.Response(200, json=body))
    result = fetch_source(SourceConfig(**kw), tmdb_token=None)
    assert [(i.title, i.imdb_id) for i in result] == [("Example", "tt0000001")]


def test_stevenlu(respx_mock):
    respx_mock.get("https://s3.amazonaws.com/popular-movies/movies.json").mock(
        return_value=httpx.Response(200, json=[{"title": "Example", "imdb_id": "tt0000001"}])
    )
    assert fetch_source(SourceConfig(type="stevenlu"), tmdb_token=None)[0].imdb_id == "tt0000001"


@pytest.mark.parametrize("mode", ["popular", "trending", "list"])
def test_tmdb_pages(respx_mock, mode):
    kw = {"type": "tmdb", "mode": mode}
    path = "/4/list/42"
    if mode != "list":
        kw.update(media_type="series", limit=2)
        path = "/3/tv/popular" if mode == "popular" else "/3/trending/tv/week"
    else:
        kw["list_id"] = 42
    route = respx_mock.get("https://api.themoviedb.org" + path)
    route.side_effect = [
        httpx.Response(
            200,
            json={
                "page": n,
                "total_pages": 2,
                "results": [{"id": n, "name": f"Show {n}", "media_type": "tv"}],
            },
        )
        for n in (1, 2)
    ]
    result = fetch_source(SourceConfig(**kw), tmdb_token="read-secret")
    assert [i.tmdb_id for i in result] == [1, 2]


def test_plex_pages(respx_mock):
    respx_mock.get(
        "https://discover.provider.plex.tv/library/sections/watchlist/all"
    ).side_effect = [
        httpx.Response(
            200,
            json={
                "MediaContainer": {
                    "totalSize": 2,
                    "Metadata": [
                        {"title": "Movie", "type": "movie", "Guid": [{"id": "imdb://tt0000001"}]}
                    ],
                }
            },
        ),
        httpx.Response(
            200,
            json={
                "MediaContainer": {
                    "totalSize": 2,
                    "Metadata": [{"title": "Show", "type": "show", "Guid": [{"id": "tvdb://42"}]}],
                }
            },
        ),
    ]
    result = fetch_source(SourceConfig(type="plex_watchlist", token="plex-secret"), tmdb_token=None)
    assert [i.kind for i in result] == ["movie", "series"]
    assert result[1].tvdb_id == 42


@pytest.mark.parametrize(
    "body",
    [{}, [{"title": "Bad", "imdb_id": "not-an-id"}], [{"title": "Bad", "imdb_id": True}], [None]],
)
def test_bad_source_shape_fails(respx_mock, body):
    respx_mock.get("https://s3.amazonaws.com/popular-movies/movies.json").respond(200, json=body)
    with pytest.raises(IntegrationError):
        fetch_source(SourceConfig(type="stevenlu"), tmdb_token=None)


def test_later_page_failure_and_repeated_page(respx_mock):
    route = respx_mock.get("https://api.themoviedb.org/4/list/42")
    route.side_effect = [
        httpx.Response(
            200,
            json={
                "page": 1,
                "total_pages": 2,
                "results": [{"id": 1, "title": "Movie", "media_type": "movie"}],
            },
        )
    ] * 2
    with pytest.raises(IntegrationError):
        fetch_source(SourceConfig(type="tmdb", mode="list", list_id=42), tmdb_token="secret")
