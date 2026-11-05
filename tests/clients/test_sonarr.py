import json

import httpx
import pytest
import respx

from excludarr.clients.sonarr import SonarrClient
from excludarr.config import Integration

API = "http://sonarr.test/api/v3"


def make() -> SonarrClient:
    return SonarrClient(Integration(url="http://sonarr.test", api_key="k"))


@respx.mock
@pytest.mark.parametrize(
    "kwargs, expected",
    [
        (
            {"episode_ids": [1, 2], "season": 3},
            {"name": "EpisodeSearch", "episodeIds": [1, 2]},
        ),
        ({"season": 3}, {"name": "SeasonSearch", "seriesId": 7, "seasonNumber": 3}),
        ({}, {"name": "SeriesSearch", "seriesId": 7}),
    ],
)
def test_search_picks_command(kwargs, expected):
    cmd = respx.post(f"{API}/command").mock(return_value=httpx.Response(201, json={}))
    make().search(7, **kwargs)
    assert json.loads(cmd.calls[0].request.content) == expected


@respx.mock
def test_delete_series_uses_import_list_exclusion_param():
    route = respx.delete(f"{API}/series/5").mock(return_value=httpx.Response(200))
    make().delete_series(5, delete_files=True, add_exclusion=False)
    q = route.calls[0].request.url.query.decode()
    assert "deleteFiles=true" in q and "addImportListExclusion=false" in q


@respx.mock
def test_set_episodes_monitored_body():
    route = respx.put(f"{API}/episode/monitor").mock(return_value=httpx.Response(202, json={}))
    make().set_episodes_monitored([1, 2], False)
    assert json.loads(route.calls[0].request.content) == {
        "episodeIds": [1, 2],
        "monitored": False,
    }


@respx.mock
def test_sonarr_sends_api_key_and_ensure_tag_case_insensitive():
    s = respx.get(f"{API}/series").mock(return_value=httpx.Response(200, json=[{"id": 1}]))
    assert make().series() == [{"id": 1}]
    assert s.calls[0].request.headers["X-Api-Key"] == "k"
    respx.get(f"{API}/tag").mock(return_value=httpx.Response(200, json=[{"id": 1, "label": "foo"}]))
    post = respx.post(f"{API}/tag").mock(return_value=httpx.Response(200, json={"id": 2}))
    c = make()
    assert c.ensure_tag("Foo") == 1
    assert not post.called
    assert c.ensure_tag("bar") == 2


@respx.mock
def test_sonarr_misc_endpoints():
    ep = respx.get(f"{API}/episode").mock(return_value=httpx.Response(200, json=[{"id": 1}]))
    assert make().episodes(3) == [{"id": 1}]
    assert ep.calls[0].request.url.params["seriesId"] == "3"
    ef = respx.get(f"{API}/episodefile").mock(return_value=httpx.Response(200, json=[{"id": 9}]))
    assert make().episode_files(3) == [{"id": 9}]
    assert ef.calls[0].request.url.params["seriesId"] == "3"
    respx.put(f"{API}/series/3").mock(return_value=httpx.Response(202))
    make().update_series({"id": 3})
    bulk = respx.delete(f"{API}/episodefile/bulk").mock(return_value=httpx.Response(200))
    make().delete_episode_files([9])
    assert json.loads(bulk.calls[0].request.content) == {"episodeFileIds": [9]}
    ex = respx.post(f"{API}/importlistexclusion").mock(return_value=httpx.Response(201, json={}))
    make().add_exclusion(11, "T")
    assert json.loads(ex.calls[0].request.content) == {"tvdbId": 11, "title": "T"}
    respx.get(f"{API}/queue").mock(return_value=httpx.Response(200, json={"records": [{"id": 4}]}))
    assert make().queue() == [{"id": 4}]
    rq = respx.delete(f"{API}/queue/4").mock(return_value=httpx.Response(200))
    make().remove_queue_item(4)
    q = rq.calls[0].request.url.query.decode()
    assert "removeFromClient=true" in q and "blocklist=false" in q


@respx.mock
def test_search_empty_episode_ids_is_noop():
    cmd = respx.post(f"{API}/command").mock(return_value=httpx.Response(201, json={}))
    make().search(7, episode_ids=[])
    make().search(7, season=3, episode_ids=[])
    assert not cmd.called


@respx.mock
def test_get_series_by_id():
    respx.get(f"{API}/series/7").mock(return_value=httpx.Response(200, json={"id": 7}))
    assert make().get_series_by_id(7) == {"id": 7}
