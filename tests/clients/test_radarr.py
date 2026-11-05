import json

import httpx
import respx

from excludarr.clients.radarr import RadarrClient
from excludarr.config import Integration

API = "http://radarr.test/api/v3"


def make() -> RadarrClient:
    return RadarrClient(Integration(url="http://radarr.test", api_key="k"))


@respx.mock
def test_radarr_sends_api_key():
    route = respx.get(f"{API}/movie").mock(return_value=httpx.Response(200, json=[{"id": 1}]))
    assert make().movies() == [{"id": 1}]
    assert route.calls[0].request.headers["X-Api-Key"] == "k"


@respx.mock
def test_radarr_delete_movie_params():
    route = respx.delete(f"{API}/movie/5").mock(return_value=httpx.Response(200))
    make().delete_movie(5, delete_files=True, add_exclusion=False)
    q = route.calls[0].request.url.query.decode()
    assert "deleteFiles=true" in q and "addImportExclusion=false" in q


@respx.mock
def test_radarr_ensure_tag_creates_missing():
    respx.get(f"{API}/tag").mock(return_value=httpx.Response(200, json=[{"id": 1, "label": "a"}]))
    post = respx.post(f"{API}/tag").mock(
        return_value=httpx.Response(200, json={"id": 2, "label": "b"})
    )
    c = make()
    assert c.tags() == {1: "a"}
    assert c.ensure_tag("a") == 1
    assert not post.called
    assert c.ensure_tag("b") == 2
    assert json.loads(post.calls[0].request.content) == {"label": "b"}


@respx.mock
def test_radarr_misc_endpoints():
    respx.put(f"{API}/movie/3").mock(return_value=httpx.Response(202))
    make().update_movie({"id": 3})
    files = respx.get(f"{API}/moviefile").mock(return_value=httpx.Response(200, json=[{"id": 9}]))
    assert make().movie_files(3) == [{"id": 9}]
    assert files.calls[0].request.url.params["movieId"] == "3"
    bulk = respx.delete(f"{API}/moviefile/bulk").mock(return_value=httpx.Response(200))
    make().delete_movie_files([9])
    assert json.loads(bulk.calls[0].request.content) == {"movieFileIds": [9]}
    ex = respx.post(f"{API}/exclusions").mock(return_value=httpx.Response(201, json={}))
    make().add_exclusion(11, "T", 2000)
    assert json.loads(ex.calls[0].request.content) == {
        "tmdbId": 11,
        "movieTitle": "T",
        "movieYear": 2000,
    }
    cmd = respx.post(f"{API}/command").mock(return_value=httpx.Response(201, json={}))
    make().search([1, 2])
    assert json.loads(cmd.calls[0].request.content) == {"name": "MoviesSearch", "movieIds": [1, 2]}
    respx.get(f"{API}/queue").mock(return_value=httpx.Response(200, json={"records": [{"id": 4}]}))
    assert make().queue() == [{"id": 4}]
    rq = respx.delete(f"{API}/queue/4").mock(return_value=httpx.Response(200))
    make().remove_queue_item(4)
    q = rq.calls[0].request.url.query.decode()
    assert "removeFromClient=true" in q and "blocklist=false" in q


@respx.mock
def test_radarr_ensure_tag_case_insensitive():
    respx.get(f"{API}/tag").mock(return_value=httpx.Response(200, json=[{"id": 1, "label": "foo"}]))
    post = respx.post(f"{API}/tag")
    assert make().ensure_tag("Foo") == 1
    assert not post.called


@respx.mock
def test_radarr_get_movie():
    respx.get(f"{API}/movie/5").mock(return_value=httpx.Response(200, json={"id": 5}))
    assert make().get_movie(5) == {"id": 5}
