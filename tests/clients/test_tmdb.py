import pytest

from excludarr.clients.http import IntegrationError
from excludarr.clients.tmdb import TmdbClient
from excludarr.lists.items import ListItem


def test_enrich_by_external_identity(respx_mock):
    respx_mock.get("https://api.themoviedb.org/3/find/tt0000001").respond(
        200, json={"movie_results": [{"id": 1}], "tv_results": []}
    )
    respx_mock.get("https://api.themoviedb.org/3/movie/1").respond(
        200,
        json={
            "id": 1,
            "title": "Example",
            "release_date": "2025-01-01",
            "vote_average": 7.5,
            "genres": [{"name": "Drama"}],
            "external_ids": {"imdb_id": "tt0000001"},
        },
    )
    result = TmdbClient("secret").enrich(
        ListItem("Example", "movie", imdb_id="tt0000001"),
        frozenset({"tmdb_id", "genres", "ratings", "year"}),
    )
    assert result.tmdb_id == 1
    assert result.genres == frozenset({"Drama"})
    assert result.ratings == {"tmdb": 7.5}
    assert result.year == 2025


def test_missing_and_conflicting_ids(respx_mock):
    respx_mock.get("https://api.themoviedb.org/3/tv/1").respond(
        200, json={"id": 1, "name": "Show", "external_ids": {"tvdb_id": 42}, "status": "Ended"}
    )
    client = TmdbClient("secret")
    assert (
        client.enrich(ListItem("Show", "series", tmdb_id=1), frozenset({"tvdb_id"})).tvdb_id == 42
    )
    with pytest.raises(IntegrationError):
        client.enrich(ListItem("Show", "series", tmdb_id=1, tvdb_id=43), frozenset({"ended"}))


def test_conflict_error_preserves_safe_reason(respx_mock):
    respx_mock.get("https://api.themoviedb.org/3/tv/1").respond(
        200, json={"id": 1, "external_ids": {"tvdb_id": 42}}
    )
    with pytest.raises(IntegrationError, match="conflicting external ID"):
        TmdbClient("secret").enrich(
            ListItem("Show", "series", tmdb_id=1, tvdb_id=43), frozenset({"ended"})
        )
