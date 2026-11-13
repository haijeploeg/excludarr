from datetime import UTC, datetime

import pytest

from dev import companions, stack


def test_episode_scan_waits_for_both_required_identities():
    show = {"ratingKey": "60"}
    partial = [
        {
            "ratingKey": "70",
            "grandparentRatingKey": "60",
            "parentRatingKey": "61",
            "title": "Pilot",
            "parentIndex": 1,
            "index": 1,
        }
    ]
    with pytest.raises(stack.SetupError, match="episode"):
        companions.episode_history(show, partial, "8")
    complete = partial + [
        {
            "ratingKey": "80",
            "grandparentRatingKey": "60",
            "parentRatingKey": "62",
            "title": "Seven Thirty-Seven",
            "parentIndex": 2,
            "index": 1,
        }
    ]
    rows = companions.episode_history(show, complete, "8")
    assert [
        (row["rating_key"], row["grandparent"], row["season"], row["days"]) for row in rows
    ] == [("70", 60, 1, 1), ("80", 60, 2, 90)]


@pytest.mark.parametrize(
    "stale",
    [
        {"rating_key": "old-key", "user_id": 1234},
        {"rating_key": "42", "user_id": 9999},
    ],
)
def test_history_reconciliation_removes_only_owned_stale_rows(monkeypatch, stale):
    rows = [
        {"row_id": 1, "player": "Excludarr Dev Seed", **stale},
        {"row_id": 2, "rating_key": "42", "player": "Plex Web"},
    ]
    removed = []

    def api(service, method, path, **kwargs):
        params = kwargs["params"]
        if params["cmd"] == "delete_history":
            removed.extend(params["row_ids"].split(","))
            rows[:] = [row for row in rows if str(row["row_id"]) not in removed]
            return {"response": {"result": "success"}}
        return {"response": {"result": "success", "data": {"data": rows}}}

    monkeypatch.setattr(stack, "request", api)
    companions.reconcile_history()
    assert removed == ["1"]
    assert rows == [{"row_id": 2, "rating_key": "42", "player": "Plex Web"}]


@pytest.mark.parametrize(
    "changed", [{"user_id": 9999}, {"date": 0}, {"grandparent_rating_key": 9999}]
)
def test_history_readback_rejects_wrong_user_date_or_hierarchy(changed):
    now = datetime(2026, 11, 11, tzinfo=UTC)
    state = {
        "user": {"id": 1234, "name": "dev-viewer"},
        "items": [
            {
                "rating_key": "70",
                "type": "episode",
                "days": 1,
                "grandparent": 60,
                "season": 1,
                "episode": 1,
            }
        ],
    }
    row = {
        "rating_key": "70",
        "user_id": 1234,
        "user": "dev-viewer",
        "date": 1794268800,
        "watched_status": 1,
        "grandparent_rating_key": 60,
        "parent_media_index": 1,
        "media_index": 1,
    }
    assert companions.history_matches([row], state, now)
    assert not companions.history_matches([row | changed], state, now)


def test_seerr_seed_encodes_search_and_reuses_requests(respx_mock):
    state = {
        "movies": {"grace": {"external_id": 155}},
        "series": {"episodes": {"external_id": 81189, "title": "Breaking Bad"}},
    }
    respx_mock.get(
        "http://seerr:5055/api/v1/search", params={"query": "Breaking%20Bad", "page": 1}
    ).respond(200, json={"results": [{"id": 1396, "mediaType": "tv"}]})
    respx_mock.get("http://seerr:5055/api/v1/tv/1396").respond(
        200, json={"externalIds": {"tvdbId": 81189}}
    )
    respx_mock.get("http://seerr:5055/api/v1/request").respond(
        200,
        json={
            "results": [
                {"id": 7, "type": "movie", "media": {"id": 70, "tmdbId": 155}},
                {"id": 8, "type": "tv", "media": {"id": 80, "tmdbId": 1396}},
            ]
        },
    )
    result = companions.seed_seerr(state)
    assert result["movies"]["request_id"] == 7
    assert result["series"]["media_id"] == 80


def test_seerr_request_seed_resets_only_fixture_availability(respx_mock):
    respx_mock.get("http://seerr:5055/api/v1/request").respond(200, json={"results": []})
    respx_mock.get("http://seerr:5055/api/v1/tv/1396").respond(200, json={"mediaInfo": {"id": 9}})
    cleared = respx_mock.delete("http://seerr:5055/api/v1/media/9").respond(204)
    respx_mock.post("http://seerr:5055/api/v1/request").respond(
        201, json={"id": 8, "type": "tv", "media": {"id": 90, "tmdbId": 1396}}
    )
    respx_mock.get("http://seerr:5055/api/v1/request/8").respond(
        200, json={"id": 8, "type": "tv", "media": {"id": 90, "tmdbId": 1396}}
    )
    result = companions.ensure_seerr_request("tv", 1396)
    assert cleared.called
    assert result["id"] == 8


def test_seerr_request_seed_rejects_202_without_request_id(respx_mock):
    respx_mock.get("http://seerr:5055/api/v1/request").respond(200, json={"results": []})
    respx_mock.get("http://seerr:5055/api/v1/tv/1396").respond(200, json={})
    respx_mock.post("http://seerr:5055/api/v1/request").respond(
        202, json={"message": "No seasons available to request"}
    )
    with pytest.raises(stack.SetupError, match="did not create"):
        companions.ensure_seerr_request("tv", 1396)
