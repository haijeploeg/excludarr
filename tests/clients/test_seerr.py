from datetime import UTC, datetime

import httpx
import respx

from excludarr.clients.seerr import SeerrClient
from excludarr.config import Integration

API = "http://seerr.test/api/v1"


def req(i, **kw):
    return {
        "id": i,
        "type": "tv",
        "createdAt": "2024-05-01T10:00:00.000Z",
        "media": {"id": 50 + i, "tmdbId": 10 + i, "tvdbId": 20 + i, "mediaType": "tv"},
        "requestedBy": {"plexUsername": "Bob", "displayName": "Bobby", "email": None},
        "seasons": [{"seasonNumber": 1}],
    } | kw


@respx.mock
def test_requests_paging():
    def handler(request):
        skip = int(request.url.params["skip"])
        results = [req(1)] if skip == 0 else [req(2)]  # skip advances by len(results)
        return httpx.Response(200, json={"pageInfo": {"pages": 2}, "results": results})

    route = respx.get(f"{API}/request").mock(side_effect=handler)
    out = SeerrClient(Integration(url="http://seerr.test", api_key="k")).requests()
    assert [r.id for r in out] == [1, 2]
    assert [c.request.url.params["skip"] for c in route.calls] == ["0", "1"]
    assert route.calls[0].request.headers["X-Api-Key"] == "k"
    assert out[0].created_at == datetime(2024, 5, 1, 10, tzinfo=UTC)
    assert out[0].requested_by == {"bob", "bobby"}
    assert out[0].seasons == {1}


@respx.mock
def test_seerr_deletes():
    m = respx.delete(f"{API}/media/5").mock(return_value=httpx.Response(204))
    r = respx.delete(f"{API}/request/7").mock(return_value=httpx.Response(204))
    c = SeerrClient(Integration(url="http://seerr.test", api_key="k"))
    c.delete_media(5)
    c.delete_request(7)
    assert m.called and r.called
