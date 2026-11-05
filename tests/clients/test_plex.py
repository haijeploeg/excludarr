import httpx
import respx

from excludarr.clients.plex import PlexClient, PlexItem
from excludarr.config import PlexIntegration

BASE = "http://plex.test"


def make() -> PlexClient:
    return PlexClient(PlexIntegration(url=BASE, token="tok"))


@respx.mock
def test_items_by_guid_maps_all_guids():
    sections = respx.get(f"{BASE}/library/sections").mock(
        return_value=httpx.Response(
            200,
            json={
                "MediaContainer": {
                    "Directory": [
                        {"key": "1", "type": "movie"},
                        {"key": "2", "type": "show"},
                        {"key": "3", "type": "artist"},
                        {"key": "4", "type": "movie"},
                    ]
                }
            },
        )
    )
    respx.get(f"{BASE}/library/sections/1/all").mock(
        return_value=httpx.Response(
            200,
            json={
                "MediaContainer": {
                    "Metadata": [
                        {"ratingKey": "10", "Guid": [{"id": "tmdb://603"}, {"id": "imdb://tt1"}]}
                    ]
                }
            },
        )
    )
    respx.get(f"{BASE}/library/sections/2/all").mock(
        return_value=httpx.Response(
            200,
            json={
                "MediaContainer": {"Metadata": [{"ratingKey": 20, "Guid": [{"id": "tvdb://81"}]}]}
            },
        )
    )
    respx.get(f"{BASE}/library/sections/4/all").mock(
        return_value=httpx.Response(200, json={"MediaContainer": {"size": 0}})
    )
    got = make().items_by_guid()
    movie, show = PlexItem("10", "1", "movie"), PlexItem("20", "2", "show")
    assert got == {
        ("movie", "tmdb://603"): movie,
        ("movie", "imdb://tt1"): movie,
        ("show", "tvdb://81"): show,
    }
    assert sections.calls[0].request.headers["X-Plex-Token"] == "tok"
    assert sections.calls[0].request.headers["Accept"] == "application/json"


def mock_metadata(collections):
    meta = {"ratingKey": "10", "Collection": [{"tag": t} for t in collections]}
    return respx.get(f"{BASE}/library/metadata/10").mock(
        return_value=httpx.Response(200, json={"MediaContainer": {"Metadata": [meta]}})
    )


@respx.mock
def test_add_to_collection_keeps_existing_collections():
    mock_metadata(["Favourites", "Classics"])
    route = respx.put(f"{BASE}/library/sections/1/all").mock(return_value=httpx.Response(200))
    make().add_to_collection(PlexItem("10", "1", "movie"), "Leaving Soon")
    p = route.calls[0].request.url.params
    assert p["type"] == "1" and p["id"] == "10" and p["collection.locked"] == "1"
    assert [p[f"collection[{i}].tag.tag"] for i in range(3)] == [
        "Favourites",
        "Classics",
        "Leaving Soon",
    ]
    assert "collection[3].tag.tag" not in p


@respx.mock
def test_add_to_collection_dedupes_case_insensitively():
    mock_metadata(["leaving soon"])
    route = respx.put(f"{BASE}/library/sections/1/all").mock(return_value=httpx.Response(200))
    make().add_to_collection(PlexItem("10", "1", "movie"), "Leaving Soon")
    p = route.calls[0].request.url.params
    assert p["collection[0].tag.tag"] == "leaving soon" and "collection[1].tag.tag" not in p


@respx.mock
def test_remove_from_collection_and_refresh():
    route = respx.put(f"{BASE}/library/sections/2/all").mock(return_value=httpx.Response(200))
    make().remove_from_collection(PlexItem("20", "2", "show"), "Leaving Soon")
    p = route.calls[0].request.url.params
    assert p["type"] == "2" and p["collection[].tag.tag-"] == "Leaving Soon"
    ref = respx.get(f"{BASE}/library/sections/2/refresh").mock(return_value=httpx.Response(200))
    make().refresh("2")
    assert ref.called
