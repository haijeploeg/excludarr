import copy
from datetime import UTC, datetime

from excludarr.actions import execute
from excludarr.clients.plex import PlexItem
from excludarr.clients.seerr import SeerrRequest
from excludarr.config import Config, Rule
from excludarr.facts import Clients, Context
from excludarr.items import EpisodeRef, MediaItem
from excludarr.storage.repo import Repo

NOW = datetime(2026, 1, 1, tzinfo=UTC)


class Fake:
    """Records every method call; `returns` maps method name to a return value or exception.

    get_movie / get_series_by_id return the last update_* payload (server state),
    starting from a copy of MOVIE_RAW / SERIES_RAW.
    """

    def __init__(self, **returns):
        self.returns, self.calls = returns, []
        returns.setdefault("get_movie", copy.deepcopy(MOVIE_RAW))
        returns.setdefault("get_series_by_id", copy.deepcopy(SERIES_RAW))

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.calls.append((name, *args, *kwargs.items()))
            if name in ("update_movie", "update_series"):
                self.returns["get_" + ("movie" if name == "update_movie" else "series_by_id")] = (
                    args[0]
                )
            ret = self.returns.get(name)
            if isinstance(ret, Exception):
                raise ret
            return ret

        return call

    def names(self):
        return [c[0] for c in self.calls]


def ctx_with(tmp_path, minimal_cfg, **clients):
    cfg = Config.model_validate(minimal_cfg)
    return Context(cfg, Clients(**clients), Repo(f"sqlite:///{tmp_path / 'db.sqlite'}"), NOW)


def rule(target, action, **kw):
    return Rule.model_validate(
        {"name": "r", "target": target, "action": action, "when": {"monitored": True}, **kw}
    )


MOVIE_RAW = {"id": 7, "title": "M", "monitored": True, "tags": []}


def movie(**kw):
    return MediaItem(
        key="radarr:movie:7", kind="movie", title="M (2000)", base_title="M", arr_id=7,
        tmdb_id=11, year=2000, size_bytes=500, has_file=True, raw=MOVIE_RAW, **kw,
    )  # fmt: skip


SERIES_RAW = {
    "id": 3,
    "title": "S",
    "monitored": True,
    "tags": [],
    "seasons": [{"seasonNumber": 1, "monitored": True}, {"seasonNumber": 2, "monitored": True}],
}


def season(n=1, file_ids=(101, None)):
    eps = tuple(
        EpisodeRef(n * 10 + i, n, i, True, f, 100 if f else 0, True)
        for i, f in enumerate(file_ids, 1)
    )
    return MediaItem(
        key=f"sonarr:season:3:{n}", kind="season", title=f"S – S{n:02d}", base_title="S",
        arr_id=3, season=n, tmdb_id=10, tvdb_id=6, size_bytes=sum(e.size_bytes for e in eps),
        has_file=any(file_ids), episodes=eps, raw=SERIES_RAW,
    )  # fmt: skip


def req(id, media_id, seasons):
    return SeerrRequest(id, media_id, "tv", 10, 6, NOW, frozenset(), frozenset(seasons))


def test_delete_files_keeps_movie_unmonitored(tmp_path, minimal_cfg):
    radarr = Fake(movie_files=[{"id": 1}, {"id": 2}], queue=[])
    item = movie()
    res = execute(
        rule("radarr", "delete_files"), item, ctx_with(tmp_path, minimal_cfg, radarr=radarr)
    )
    assert res.ok and res.size_freed == 500 and res.side_effect_errors == []
    assert ("delete_movie_files", [1, 2]) in radarr.calls
    assert ("update_movie", {**item.raw, "monitored": False}) in radarr.calls
    assert "delete_movie" not in radarr.names()
    assert item.raw["monitored"] is True  # the item's raw dict is not mutated


def test_movie_delete_without_files_frees_nothing(tmp_path, minimal_cfg):
    radarr = Fake(queue=[])
    r = rule("radarr", "delete", import_exclusion=True)
    res = execute(r, movie(), ctx_with(tmp_path, minimal_cfg, radarr=radarr))
    assert res.ok and res.size_freed == 0
    assert ("delete_movie", 7, False, True) in radarr.calls


def test_season_delete_removes_files_and_unmonitors(tmp_path, minimal_cfg):
    sonarr = Fake(queue=[])
    item = season()
    res = execute(rule("sonarr", "delete"), item, ctx_with(tmp_path, minimal_cfg, sonarr=sonarr))
    assert res.ok and res.size_freed == 100
    assert ("delete_episode_files", [101]) in sonarr.calls
    assert ("set_episodes_monitored", [11, 12], False) in sonarr.calls
    updated = next(c[1] for c in sonarr.calls if c[0] == "update_series")
    assert updated["seasons"] == [
        {"seasonNumber": 1, "monitored": False},
        {"seasonNumber": 2, "monitored": True},
    ]
    assert SERIES_RAW["seasons"][0]["monitored"] is True


def test_season_delete_without_files_still_unmonitors(tmp_path, minimal_cfg):
    sonarr = Fake(queue=[])
    item = season(file_ids=(None, None))
    res = execute(rule("sonarr", "delete"), item, ctx_with(tmp_path, minimal_cfg, sonarr=sonarr))
    assert res.ok and res.size_freed == 0
    assert "delete_episode_files" not in sonarr.names()
    assert ("set_episodes_monitored", [11, 12], False) in sonarr.calls


def test_monitor_with_search_triggers_season_search(tmp_path, minimal_cfg):
    sonarr = Fake()
    r = rule("sonarr", "monitor", search=True)
    res = execute(r, season(2), ctx_with(tmp_path, minimal_cfg, sonarr=sonarr))
    assert res.ok and res.size_freed == 0
    assert sonarr.names() == [
        "get_series_by_id", "update_series", "set_episodes_monitored", "search"
    ]  # fmt: skip
    assert sonarr.calls[1][1]["seasons"][1] == {"seasonNumber": 2, "monitored": True}
    assert sonarr.calls[2] == ("set_episodes_monitored", [21, 22], True)
    assert sonarr.calls[3] == ("search", 3, ("season", 2))


def test_two_seasons_of_one_series_never_resend_stale_flags(tmp_path, minimal_cfg):
    sonarr = Fake()
    ctx = ctx_with(tmp_path, minimal_cfg, sonarr=sonarr)
    execute(rule("sonarr", "unmonitor"), season(1), ctx)
    execute(rule("sonarr", "unmonitor"), season(2), ctx)
    last = [c[1] for c in sonarr.calls if c[0] == "update_series"][-1]
    assert last["seasons"] == [
        {"seasonNumber": 1, "monitored": False},
        {"seasonNumber": 2, "monitored": False},
    ]


def series_item():
    s = season()
    s.kind, s.season, s.size_bytes = "series", None, 300
    return s


def test_series_delete_passes_options(tmp_path, minimal_cfg):
    sonarr = Fake(queue=[])
    r = rule("sonarr", "delete", level="series", delete_files=True, import_exclusion=True)
    res = execute(r, series_item(), ctx_with(tmp_path, minimal_cfg, sonarr=sonarr))
    assert res.ok and res.size_freed == 300
    assert ("delete_series", 3, True, True) in sonarr.calls


def test_series_delete_files_deletes_all_and_unmonitors(tmp_path, minimal_cfg):
    sonarr = Fake(queue=[], episode_files=[{"id": 1}, {"id": 2}, {"id": 3}])
    r = rule("sonarr", "delete_files", level="series")
    res = execute(r, series_item(), ctx_with(tmp_path, minimal_cfg, sonarr=sonarr))
    assert res.ok and res.size_freed == 300
    assert ("delete_episode_files", [1, 2, 3]) in sonarr.calls
    assert ("update_series", {**SERIES_RAW, "monitored": False}) in sonarr.calls
    assert "delete_series" not in sonarr.names()


def test_unconfigured_target_client(tmp_path, minimal_cfg):
    res = execute(rule("sonarr", "delete"), season(), ctx_with(tmp_path, minimal_cfg))
    assert not res.ok and res.detail == "sonarr not configured"
    res = execute(rule("radarr", "delete"), movie(), ctx_with(tmp_path, minimal_cfg))
    assert not res.ok and res.detail == "radarr not configured"


def test_episode_monitor_search_uses_episode_ids(tmp_path, minimal_cfg):
    sonarr = Fake()
    ep = season()
    ep.kind, ep.episode, ep.episodes = "episode", 1, ep.episodes[:1]
    execute(
        rule("sonarr", "monitor", search=True), ep, ctx_with(tmp_path, minimal_cfg, sonarr=sonarr)
    )
    assert sonarr.calls == [
        ("set_episodes_monitored", [11], True),
        ("search", 3, ("episode_ids", [11])),
    ]


def test_tag_adds_tag_to_parent_series(tmp_path, minimal_cfg):
    sonarr = Fake(ensure_tag=5)
    r = rule("sonarr", "tag", tag="leaving")
    execute(r, season(), ctx_with(tmp_path, minimal_cfg, sonarr=sonarr))
    assert ("ensure_tag", "leaving") in sonarr.calls
    assert ("update_series", {**SERIES_RAW, "tags": [5]}) in sonarr.calls


def test_import_exclusion_movie(tmp_path, minimal_cfg):
    radarr = Fake()
    execute(
        rule("radarr", "import_exclusion"), movie(), ctx_with(tmp_path, minimal_cfg, radarr=radarr)
    )
    assert radarr.calls == [("add_exclusion", 11, "M", 2000)]


def test_side_effect_failure_does_not_fail_action(tmp_path, minimal_cfg):
    radarr = Fake(queue=[])
    seerr = Fake(requests=[SeerrRequest(1, 9, "movie", 11, None, NOW, frozenset(), frozenset())])
    seerr.returns["delete_media"] = RuntimeError("seerr down")
    ctx = ctx_with(tmp_path, minimal_cfg, radarr=radarr, seerr=seerr)
    res = execute(rule("radarr", "delete", delete_files=True), movie(), ctx)
    assert res.ok and res.size_freed == 500
    assert len(res.side_effect_errors) == 1 and "seerr down" in res.side_effect_errors[0]


def test_seerr_unavailable_is_recorded(tmp_path, minimal_cfg):
    seerr = Fake(requests=RuntimeError("boom"))
    ctx = ctx_with(tmp_path, minimal_cfg, radarr=Fake(queue=[]), seerr=seerr)
    res = execute(rule("radarr", "delete"), movie(), ctx)
    assert res.ok and len(res.side_effect_errors) == 1


def test_main_action_failure_skips_side_effects(tmp_path, minimal_cfg):
    radarr = Fake(delete_movie=RuntimeError("radarr 500"), queue=[])
    seerr, plex = Fake(requests=[]), Fake(items_by_guid={})
    ctx = ctx_with(tmp_path, minimal_cfg, radarr=radarr, seerr=seerr, plex=plex)
    res = execute(rule("radarr", "delete"), movie(), ctx)
    assert not res.ok and res.detail == "radarr 500" and res.size_freed == 0
    assert radarr.names() == ["delete_movie"]
    assert seerr.calls == [] and plex.calls == []


def test_seerr_season_request_deleted_only_when_all_requested_seasons_empty(tmp_path, minimal_cfg):
    # After deleting season 1, season 2 still has a file.
    sonarr = Fake(queue=[], episode_files=[{"id": 201, "seasonNumber": 2}])
    reqs = [req(1, 9, {1}), req(2, 9, {1, 2}), req(3, 9, {2})]
    seerr = Fake(requests=reqs)
    ctx = ctx_with(tmp_path, minimal_cfg, sonarr=sonarr, seerr=seerr)
    res = execute(rule("sonarr", "delete"), season(1), ctx)
    assert res.ok and res.side_effect_errors == []
    assert ("episode_files", 3) in sonarr.calls
    assert [c for c in seerr.calls if c[0] != "requests"] == [("delete_request", 1)]


def test_queue_items_removed_on_delete(tmp_path, minimal_cfg):
    queue = [
        {"id": 1, "seriesId": 3, "episodeId": 11},
        {"id": 2, "seriesId": 3, "episodeId": 21},  # other season
        {"id": 3, "seriesId": 4, "episodeId": 11},  # other series
    ]
    sonarr = Fake(queue=queue)
    execute(rule("sonarr", "delete"), season(), ctx_with(tmp_path, minimal_cfg, sonarr=sonarr))
    assert [c for c in sonarr.calls if c[0] == "remove_queue_item"] == [("remove_queue_item", 1)]

    sonarr = Fake(queue=queue)
    r = rule("sonarr", "delete", level="series")
    execute(r, series_item(), ctx_with(tmp_path, minimal_cfg, sonarr=sonarr))
    removed = [c for c in sonarr.calls if c[0] == "remove_queue_item"]
    assert removed == [("remove_queue_item", 1), ("remove_queue_item", 2)]

    radarr = Fake(queue=[{"id": 8, "movieId": 7}, {"id": 9, "movieId": 1}])
    execute(rule("radarr", "delete"), movie(), ctx_with(tmp_path, minimal_cfg, radarr=radarr))
    assert [c for c in radarr.calls if c[0] == "remove_queue_item"] == [("remove_queue_item", 8)]


def test_plex_refreshed_after_delete(tmp_path, minimal_cfg):
    plex = Fake(items_by_guid={("movie", "tmdb://11"): PlexItem("m1", "4", "movie")})
    ctx = ctx_with(tmp_path, minimal_cfg, radarr=Fake(queue=[]), plex=plex)
    res = execute(rule("radarr", "delete"), movie(), ctx)
    assert res.ok and ("refresh", "4") in plex.calls
