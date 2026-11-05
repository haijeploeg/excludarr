from datetime import UTC, datetime

import httpx
import pytest
import respx

from excludarr.clients.http import IntegrationError
from excludarr.clients.tautulli import TautulliClient
from excludarr.config import Integration

URL = "http://tautulli.test/api/v2"


def make() -> TautulliClient:
    return TautulliClient(Integration(url="http://tautulli.test", api_key="k"))


def row(i, **kw):
    base = {
        "date": 1700000000 + i,
        "user": "u",
        "friendly_name": "U",
        "rating_key": 100 + i,
        "grandparent_rating_key": "",
        "parent_media_index": "",
        "media_index": None,
        "media_type": "movie",
        "watched_status": 1,
    }
    return base | kw


def page(rows, total):
    return httpx.Response(
        200,
        json={"response": {"result": "success", "data": {"recordsFiltered": total, "data": rows}}},
    )


@respx.mock
def test_history_pages_until_records_filtered(monkeypatch):
    monkeypatch.setattr("excludarr.clients.tautulli.PAGE", 2)
    route = respx.get(URL).mock(
        side_effect=[
            page([row(0), row(1, watched_status=0.5)], 3),
            page(
                [
                    row(
                        2,
                        media_type="episode",
                        grandparent_rating_key="50",
                        parent_media_index="2",
                        media_index="5",
                    )
                ],
                3,
            ),
        ]
    )
    rows = make().history()
    assert [r.rating_key for r in rows] == ["100", "101", "102"]
    assert [r.watched for r in rows] == [True, False, True]
    assert rows[0].at == datetime.fromtimestamp(1700000000, UTC)
    assert rows[0].grandparent_rating_key is None and rows[0].season is None
    assert rows[0].episode is None
    assert (rows[2].grandparent_rating_key, rows[2].season, rows[2].episode) == ("50", 2, 5)
    starts = [c.request.url.params["start"] for c in route.calls]
    assert starts == ["0", "2"]
    assert route.calls[0].request.url.params["apikey"] == "k"
    assert route.calls[0].request.url.params["cmd"] == "get_history"


@respx.mock
def test_history_error_result_raises():
    respx.get(URL).mock(
        return_value=httpx.Response(
            200, json={"response": {"result": "error", "message": "Invalid apikey"}}
        )
    )
    with pytest.raises(IntegrationError, match="Invalid apikey"):
        make().history()


@pytest.mark.parametrize(
    ("status", "watched"),
    [(1, True), ("1", True), (1.0, True), (0.5, False), ("0.75", False), (0, False), (None, False)],
)
@respx.mock
def test_watched_status_parsing(status, watched):
    respx.get(URL).mock(return_value=page([row(0, watched_status=status)], 1))
    assert make().history()[0].watched is watched
