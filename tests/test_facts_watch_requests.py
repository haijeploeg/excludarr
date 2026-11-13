import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from excludarr.clients.http import IntegrationError
from excludarr.clients.plex import PlexItem
from excludarr.clients.seerr import SeerrRequest
from excludarr.clients.tautulli import HistoryRow
from excludarr.config import Config
from excludarr.facts import Clients, Context
from excludarr.items import EpisodeRef, MediaItem
from excludarr.storage.repo import Repo

NOW = datetime(2026, 1, 1, tzinfo=UTC)


class FakePlex:
    def __init__(self, items):
        self.items, self.calls = items, 0

    def items_by_guid(self):
        self.calls += 1
        return self.items


class FakeTautulli:
    def __init__(self, rows=None, exc=None):
        self.rows, self.exc, self.calls = rows or [], exc, 0

    def history(self):
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.rows


class FakeSeerr:
    def __init__(self, reqs):
        self.reqs = reqs

    def requests(self):
        return self.reqs


def row(key, days, season=None, ep=None, watched=True, gp=None):
    return HistoryRow(NOW - timedelta(days=days), "Bob", "Bobby", key, gp, season, ep, watched)


def make_ctx(tmp_path, minimal_cfg, **clients):
    cfg = Config.model_validate(minimal_cfg)
    return Context(cfg, Clients(**clients), Repo(f"sqlite:///{tmp_path / 'db.sqlite'}"), NOW)


def eps(*aired):
    return tuple(EpisodeRef(i, 1, i, a, None, 0, True) for i, a in enumerate(aired, 1))


def season(**kw):
    return MediaItem(
        key="s", kind="season", title="S", base_title="S", arr_id=1, season=1, tmdb_id=10,
        **{"episodes": eps(True, True), **kw},
    )  # fmt: skip


PLEX = {
    ("show", "tmdb://10"): PlexItem("show1", "2", "show"),
    ("movie", "tmdb://11"): PlexItem("m1", "1", "movie"),
    ("show", "imdb://tt5"): PlexItem("show5", "2", "show"),
    ("show", "tvdb://6"): PlexItem("show6", "2", "show"),
}


def plex_tautulli(rows):
    return {"plex": FakePlex(PLEX), "tautulli": FakeTautulli(rows)}


def test_watch_season_rollup_most_recent_wins(tmp_path, minimal_cfg):
    rows = [row("e1", 90, 1, 1, gp="show1"), row("e2", 10, 1, 2, gp="show1")]
    ctx = make_ctx(tmp_path, minimal_cfg, **plex_tautulli(rows))
    w = ctx.watch(season())
    assert w.last_watched == NOW - timedelta(days=10)
    assert w.play_count == 2 and w.fully_watched
    assert w.last_by_user["bob"] == w.last_by_user["bobby"] == NOW - timedelta(days=10)


def test_watch_fully_watched_requires_all_aired_episodes(tmp_path, minimal_cfg):
    rows = [row("e1", 5, 1, 1, gp="show1"), row("e2", 3, 1, 2, watched=False, gp="show1")]
    ctx = make_ctx(tmp_path, minimal_cfg, **plex_tautulli(rows))
    w = ctx.watch(season())
    assert not w.fully_watched and w.play_count == 1
    assert w.last_watched == NOW - timedelta(days=3)  # partial rows count


def test_watch_movie(tmp_path, minimal_cfg):
    ctx = make_ctx(tmp_path, minimal_cfg, **plex_tautulli([row("m1", 4), row("x", 1)]))
    m = MediaItem(key="m", kind="movie", title="M", base_title="M", arr_id=1, tmdb_id=11)
    w = ctx.watch(m)
    assert w.fully_watched and w.play_count == 1


def test_movie_viewers_use_display_names_without_aliases_or_partial_plays(tmp_path, minimal_cfg):
    rows = [
        row("m1", 4),
        row("m1", 2),
        replace(row("m1", 1, watched=False), user="Alice", friendly_name="Alice"),
        replace(row("m1", 1), user="Carol", friendly_name=""),
    ]
    ctx = make_ctx(tmp_path, minimal_cfg, **plex_tautulli(rows))
    item = MediaItem(key="m", kind="movie", title="M", base_title="M", arr_id=1, tmdb_id=11)
    assert ctx.watch(item).watched_users == ["Bobby", "Carol"]


def test_watch_unknown_when_tautulli_fails(tmp_path, minimal_cfg, caplog):
    t = FakeTautulli(exc=IntegrationError("tautulli", "down"))
    ctx = make_ctx(tmp_path, minimal_cfg, plex=FakePlex(PLEX), tautulli=t)
    with caplog.at_level(logging.WARNING):
        assert ctx.watch(season()) is None
        assert ctx.watch(season()) is None
    assert t.calls == 1
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1


def test_watch_unknown_on_malformed_rows(tmp_path, minimal_cfg):
    t = FakeTautulli(exc=KeyError("date"))
    ctx = make_ctx(tmp_path, minimal_cfg, plex=FakePlex(PLEX), tautulli=t)
    assert ctx.watch(season()) is None


def test_watch_none_when_not_in_plex(tmp_path, minimal_cfg):
    ctx = make_ctx(tmp_path, minimal_cfg, **plex_tautulli([]))
    other = MediaItem(key="m", kind="movie", title="M", base_title="M", arr_id=1, tmdb_id=99)
    assert ctx.watch(other) is None
    assert ctx.movie_viewer_labels(other) == ["Not in Plex"]


def test_viewer_labels_keep_service_failures_unknown(tmp_path, minimal_cfg):
    item = MediaItem(key="m", kind="movie", title="M", base_title="M", arr_id=1, tmdb_id=11)

    class BrokenPlex:
        def items_by_guid(self):
            raise IntegrationError("plex", "down")

    ctx = make_ctx(tmp_path, minimal_cfg, plex=BrokenPlex(), tautulli=FakeTautulli([]))
    assert ctx.movie_viewer_labels(item) is None
    ctx = make_ctx(
        tmp_path,
        minimal_cfg,
        plex=FakePlex(PLEX),
        tautulli=FakeTautulli(exc=IntegrationError("tautulli", "down")),
    )
    assert ctx.movie_viewer_labels(item) is None


def test_watch_none_when_not_configured(tmp_path, minimal_cfg):
    assert make_ctx(tmp_path, minimal_cfg).watch(season()) is None


def test_plex_fetched_once(tmp_path, minimal_cfg):
    p = FakePlex(PLEX)
    ctx = make_ctx(tmp_path, minimal_cfg, plex=p)
    ctx.plex_item(season())
    ctx.plex_item(season())
    assert p.calls == 1


def sreq(id, tmdb, seasons, mt="tv", tvdb=None):
    return SeerrRequest(id, id, mt, tmdb, tvdb, NOW, frozenset({"bob"}), frozenset(seasons))


def test_requests_season_filter(tmp_path, minimal_cfg):
    reqs = [sreq(1, 10, {1}), sreq(2, 10, {2}), sreq(3, 99, {1}, tvdb=7), sreq(4, 10, {1}, "movie")]
    ctx = make_ctx(tmp_path, minimal_cfg, seerr=FakeSeerr(reqs))
    assert [r.id for r in ctx.requests(season())] == [1]
    series = MediaItem(key="x", kind="series", title="X", base_title="X", arr_id=1, tmdb_id=10)
    assert [r.id for r in ctx.requests(series)] == [1, 2]
    by_tvdb = MediaItem(key="y", kind="series", title="Y", base_title="Y", arr_id=1, tvdb_id=7)
    assert [r.id for r in ctx.requests(by_tvdb)] == [3]


def test_requester_labels_match_seasons_and_deduplicate_names(tmp_path, minimal_cfg):
    requests = [
        replace(sreq(1, 10, {1}), requester_name="Alice"),
        replace(sreq(2, 10, {2}), requester_name="Bob"),
        replace(sreq(3, 10, {1}), requester_name="Alice"),
        replace(sreq(4, 10, {1}, "movie"), requester_name="Carol"),
    ]
    ctx = make_ctx(tmp_path, minimal_cfg, seerr=FakeSeerr(requests))
    assert ctx.requester_labels(season()) == ["Alice"]
    assert ctx.requester_labels(replace(season(), kind="series", season=None)) == ["Alice", "Bob"]
    assert ctx.requester_labels(replace(season(), kind="movie")) == ["Carol"]
    assert ctx.requester_labels(replace(season(), season=3)) == []


def test_requests_none_when_unconfigured_or_failed(tmp_path, minimal_cfg):
    assert make_ctx(tmp_path, minimal_cfg).requests(season()) is None
    assert make_ctx(tmp_path, minimal_cfg).requester_labels(season()) == ["Not configured"]

    class Boom:
        def requests(self):
            raise IntegrationError("seerr", "down")

    assert make_ctx(tmp_path, minimal_cfg, seerr=Boom()).requests(season()) is None
    assert make_ctx(tmp_path, minimal_cfg, seerr=Boom()).requester_labels(season()) is None


def mk_series(**kw):
    return MediaItem(key="x", kind="series", title="X", base_title="X", arr_id=1, **kw)


def test_plex_item_requires_matching_type(tmp_path, minimal_cfg):
    only_movie = {("movie", "tmdb://10"): PlexItem("m10", "1", "movie")}
    ctx = make_ctx(
        tmp_path, minimal_cfg, plex=FakePlex(only_movie), tautulli=FakeTautulli([row("m10", 1)])
    )
    assert ctx.plex_item(mk_series(tmdb_id=10)) is None
    assert ctx.watch(mk_series(tmdb_id=10)) is None


def test_plex_item_imdb_tvdb_fallback(tmp_path, minimal_cfg):
    ctx = make_ctx(tmp_path, minimal_cfg, plex=FakePlex(PLEX))
    assert ctx.plex_item(mk_series(tmdb_id=99, imdb_id="tt5")).rating_key == "show5"
    assert ctx.plex_item(mk_series(tvdb_id=6)).rating_key == "show6"


def test_watch_last_by_user_only_watched_rows(tmp_path, minimal_cfg):
    rows = [row("e1", 20, 1, 1, gp="show1"), row("e2", 2, 1, 2, watched=False, gp="show1")]
    w = make_ctx(tmp_path, minimal_cfg, **plex_tautulli(rows)).watch(season())
    assert w.last_by_user["bob"] == NOW - timedelta(days=20)
    assert w.last_watched == NOW - timedelta(days=2)


def test_watch_series_ignores_season_zero(tmp_path, minimal_cfg):
    rows = [row("e1", 5, 1, 1, gp="show1"), row("e2", 5, 1, 2, gp="show1")]
    rows.append(row("sp", 1, 0, 1, gp="show1"))
    series = mk_series(
        tmdb_id=10, episodes=eps(True, True) + (EpisodeRef(9, 0, 1, True, None, 0, True),)
    )
    w = make_ctx(tmp_path, minimal_cfg, **plex_tautulli(rows)).watch(series)
    assert w.fully_watched
    assert w.last_watched == NOW - timedelta(days=5)
    assert w.play_count == 2


def test_watch_episode_filter(tmp_path, minimal_cfg):
    rows = [row("e1", 30, 1, 1, gp="show1"), row("e2", 3, 1, 2, gp="show1")]
    ep = mk_series(tmdb_id=10, season=1, episode=1, episodes=eps(True))
    ep.kind = "episode"
    w = make_ctx(tmp_path, minimal_cfg, **plex_tautulli(rows)).watch(ep)
    assert w.play_count == 1 and w.fully_watched
    assert w.last_watched == NOW - timedelta(days=30)


def test_watch_unknown_when_nothing_aired(tmp_path, minimal_cfg):
    rows = [row("e1", 5, 1, 1, gp="show1")]
    ctx = make_ctx(tmp_path, minimal_cfg, **plex_tautulli(rows))
    assert ctx.watch(season(episodes=eps(False, False))) is None
    assert ctx.watch(mk_series(tmdb_id=10, episodes=eps(False))) is None
    ep = mk_series(tmdb_id=10, season=1, episode=1, episodes=eps(False))
    ep.kind = "episode"
    assert ctx.watch(ep) is None
    # Specials do not count as something to watch for a series.
    specials = (EpisodeRef(9, 0, 1, True, None, 0, True),)
    assert ctx.watch(mk_series(tmdb_id=10, episodes=specials)) is None


class BrokenPlex:
    def items_by_guid(self):
        raise IntegrationError("plex", "down")


MOVIE = MediaItem(key="m", kind="movie", title="M", base_title="M", arr_id=1, tmdb_id=11)


def test_plex_scan_records_rating_keys(tmp_path, minimal_cfg):
    ctx = make_ctx(tmp_path, minimal_cfg, **plex_tautulli([]))
    ctx.watch(MOVIE)
    assert ctx.repo.rating_keys_for("movie", ["tmdb://11"]) == {"m1"}


def test_failed_plex_scan_records_nothing(tmp_path, minimal_cfg):
    ctx = make_ctx(tmp_path, minimal_cfg, plex=BrokenPlex(), tautulli=FakeTautulli([]))
    ctx.watch(MOVIE)
    assert ctx.repo.rating_keys_for("movie", ["tmdb://11"]) == set()


def test_plex_scan_survives_storage_failure(tmp_path, minimal_cfg):
    ctx = make_ctx(tmp_path, minimal_cfg, **plex_tautulli([row("m1", 1)]))

    def boom(pairs):
        raise RuntimeError("disk full")

    ctx.repo.rating_keys_record = boom
    assert ctx.watch(MOVIE).play_count == 1


def test_watch_uses_stored_key_when_item_left_plex(tmp_path, minimal_cfg):
    ctx = make_ctx(tmp_path, minimal_cfg, plex=FakePlex({}), tautulli=FakeTautulli([row("old", 1)]))
    ctx.repo.rating_keys_record({("movie", "tmdb://11"): "old"})
    w = ctx.watch(MOVIE)
    assert w.play_count == 1 and w.fully_watched is True


def test_watch_combines_old_and_live_keys_movie(tmp_path, minimal_cfg):
    ctx = make_ctx(tmp_path, minimal_cfg, **plex_tautulli([row("old", 5), row("m1", 1)]))
    ctx.repo.rating_keys_record({("movie", "tmdb://11"): "old"})
    assert ctx.watch(MOVIE).play_count == 2


def test_watch_combines_old_and_live_keys_series(tmp_path, minimal_cfg):
    rows = [
        row("e1", 5, 1, 1, gp="oldshow"),
        row("e2", 3, 1, 2, gp="show1"),
        row("e3", 1, 2, 1, gp="oldshow"),
    ]
    ctx = make_ctx(tmp_path, minimal_cfg, **plex_tautulli(rows))
    ctx.repo.rating_keys_record({("show", "tmdb://10"): "oldshow"})
    w = ctx.watch(season())
    assert w.play_count == 2 and w.fully_watched is True


def test_watch_counts_each_row_once_after_tautulli_remap(tmp_path, minimal_cfg):
    ctx = make_ctx(tmp_path, minimal_cfg, **plex_tautulli([row("m1", 1)]))
    ctx.repo.rating_keys_record({("movie", "tmdb://11"): "old"})
    assert ctx.watch(MOVIE).play_count == 1


def test_watch_uses_stored_keys_when_plex_fails(tmp_path, minimal_cfg):
    ctx = make_ctx(tmp_path, minimal_cfg, plex=BrokenPlex(), tautulli=FakeTautulli([row("old", 1)]))
    ctx.repo.rating_keys_record({("movie", "tmdb://11"): "old"})
    assert ctx.watch(MOVIE).play_count == 1


def test_watch_unknown_without_any_key(tmp_path, minimal_cfg):
    ctx = make_ctx(tmp_path, minimal_cfg, plex=FakePlex({}), tautulli=FakeTautulli([row("old", 1)]))
    assert ctx.watch(MOVIE) is None


def test_watch_unknown_when_tautulli_fails_with_stored_keys(tmp_path, minimal_cfg):
    t = FakeTautulli(exc=IntegrationError("tautulli", "down"))
    ctx = make_ctx(tmp_path, minimal_cfg, plex=FakePlex({}), tautulli=t)
    ctx.repo.rating_keys_record({("movie", "tmdb://11"): "old"})
    assert ctx.watch(MOVIE) is None


def test_viewer_labels_not_in_plex_only_without_keys(tmp_path, minimal_cfg):
    ctx = make_ctx(tmp_path, minimal_cfg, plex=FakePlex({}), tautulli=FakeTautulli([]))
    ctx.repo.rating_keys_record({("movie", "tmdb://11"): "old"})
    assert ctx.movie_viewer_labels(MOVIE) == []
