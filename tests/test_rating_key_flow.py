"""Monitor again after Plex removed the item: the stored rating key keeps watch facts known."""

from datetime import UTC, datetime, timedelta

import pytest

from excludarr import engine
from excludarr.actions import ActionResult
from excludarr.clients.plex import PlexItem
from excludarr.clients.tautulli import HistoryRow
from excludarr.config import Config
from excludarr.facts import Clients, Context
from excludarr.items import EpisodeRef, MediaItem
from excludarr.storage.repo import Repo

NOW = datetime(2026, 1, 1, tzinfo=UTC)
STREAMABLE = {"monetization": ["flatrate"]}
NETFLIX = 8

# The "monitor again" rules of the production config.
RULES = [
    {
        "name": "Radarr monitor again",
        "target": "radarr",
        "preview": False,
        "action": "monitor",
        "search": True,
        "when": {
            "all": [{"tag": "streamed"}, {"monitored": False}, {"not": {"streaming": STREAMABLE}}]
        },
        "unless": [{"fully_watched": True}],
    },
    {
        "name": "Sonarr monitor again",
        "target": "sonarr",
        "level": "season",
        "preview": False,
        "action": "monitor",
        "search": True,
        "when": {
            "all": [{"tag": "streamed"}, {"monitored": False}, {"not": {"streaming": STREAMABLE}}]
        },
        "unless": [{"fully_watched": True}],
    },
]

# Unmonitored, tagged, files deleted: the state after "delete streamable files".
MOVIE = MediaItem(
    key="radarr:movie:1", kind="movie", title="M", base_title="M", arr_id=1, tmdb_id=1,
    monitored=False, tags=frozenset({"streamed"}),
)  # fmt: skip
SEASON = MediaItem(
    key="sonarr:season:5:1", kind="season", title="S - Season 1", base_title="S", arr_id=5,
    season=1, tvdb_id=5, monitored=False, tags=frozenset({"streamed"}),
    episodes=(EpisodeRef(51, 1, 1, True, None, 0, False),),
)  # fmt: skip
IN_PLEX = {
    ("movie", "tmdb://1"): PlexItem("100", "1", "movie"),
    ("show", "tvdb://5"): PlexItem("500", "2", "show"),
}
PLAYS = [
    HistoryRow(NOW - timedelta(days=30), "bob", "Bob", "100", None, None, None, True),
    HistoryRow(NOW - timedelta(days=30), "bob", "Bob", "501", "500", 1, 1, True),
]


class FakePlex:
    def __init__(self, library):
        self.library = library

    def items_by_guid(self):
        return self.library


class FakeTautulli:
    def __init__(self, rows):
        self.rows = rows

    def history(self):
        return self.rows


@pytest.fixture
def flow(tmp_path, monkeypatch, minimal_cfg):
    executed = []

    def fake_execute(rule, item, ctx):
        executed.append((rule.name, item.key))
        return ActionResult(True, 0, "done")

    monkeypatch.setattr(engine, "execute", fake_execute)
    monkeypatch.setattr(engine, "build_radarr_items", lambda radarr: [MOVIE])
    monkeypatch.setattr(engine, "build_sonarr_items", lambda sonarr, level: [SEASON])
    repo = Repo(f"sqlite:///{tmp_path / 'db.sqlite'}")
    cfg = Config.model_validate(
        {
            "profile": {"locale": "nl_NL", "providers": ["Netflix"]},
            "integrations": {
                **minimal_cfg["integrations"],
                "plex": {"url": "http://plex:32400", "token": "t"},
                "tautulli": {"url": "http://tautulli:8181", "api_key": "k"},
            },
            "rules": RULES,
        }
    )

    def run(*, plex_library, streaming, plays):
        """One engine run with a fresh context, as the daemon does per scheduled run."""
        plex, tautulli = FakePlex(plex_library), FakeTautulli(plays)
        ctx = Context(cfg, Clients(radarr=object(), sonarr=object(), plex=plex, tautulli=tautulli),
                      repo, NOW)  # fmt: skip
        offers = frozenset({(NETFLIX, "FLATRATE", "hd")}) if streaming else frozenset()
        ctx.provider_ids = lambda names: {NETFLIX}
        ctx.provider_names = lambda: {NETFLIX: "Netflix"}
        ctx.streaming = lambda item: [offers]
        executed.clear()
        engine.run(ctx, dry_run=False)
        return sorted(executed)

    return run


@pytest.mark.parametrize(
    ("plays", "expected"),
    [
        ([], [("Radarr monitor again", MOVIE.key), ("Sonarr monitor again", SEASON.key)]),
        (PLAYS, []),  # a watched movie or season never comes back
    ],
    ids=["unwatched-comes-back", "watched-stays-away"],
)
def test_monitor_again_after_plex_removed_the_item(flow, plays, expected):
    # Run 1: still streamable and still in Plex. Nothing to monitor; the scan stores the keys.
    assert flow(plex_library=IN_PLEX, streaming=True, plays=plays) == []
    # Run 2: Plex removed the files' items and the streaming offer is gone.
    assert flow(plex_library={}, streaming=False, plays=plays) == expected


def test_monitor_again_never_fires_for_an_item_plex_never_had(flow):
    # Intended: Plex never had the item, so `fully_watched` stays unknown and it stays away.
    assert flow(plex_library={}, streaming=False, plays=[]) == []
