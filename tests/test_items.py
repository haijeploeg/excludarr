import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from excludarr import items
from excludarr.items import build_radarr_items, build_sonarr_items

FX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FX / name).read_text())


class FakeRadarr:
    def movies(self):
        return load("radarr_movies.json")

    def tags(self):
        return {1: "keep"}


class FakeSonarr:
    def series(self):
        return load("sonarr_series.json")

    def episodes(self, sid):
        return load("sonarr_episodes.json")

    def episode_files(self, sid):
        return load("sonarr_episode_files.json")

    def tags(self):
        return {2: "classic"}


@pytest.fixture(autouse=True)
def now(monkeypatch):
    monkeypatch.setattr(items, "_now", lambda: datetime(2024, 1, 1, tzinfo=UTC))


def test_radarr_item_fields():
    dune, obscure = build_radarr_items(FakeRadarr())
    assert dune.key == "radarr:movie:1"
    assert dune.title == "Dune (2021)" and dune.base_title == "Dune"
    assert dune.tmdb_id == 438631 and dune.imdb_id == "tt1160419"
    assert dune.added == datetime(2023, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert dune.size_bytes == 5000 and dune.has_file and dune.monitored
    assert dune.tags == {"keep"} and dune.genres == {"Sci-Fi", "Adventure"}
    assert dune.ratings == {"tmdb": 7.8, "imdb": 8.0}
    assert (obscure.tmdb_id, obscure.imdb_id, obscure.ratings) == (None, None, {})
    assert not obscure.has_file and not obscure.monitored


def test_season_items_inherit_series_attributes():
    s2 = next(i for i in build_sonarr_items(FakeSonarr(), "season") if i.season == 2)
    assert (s2.tmdb_id, s2.imdb_id, s2.tvdb_id) == (1396, "tt0903747", 81189)
    assert s2.year == 2008 and s2.ended is True
    assert s2.tags == {"classic"} and s2.genres == {"Drama"}
    assert s2.ratings == {"sonarr": 8.9} and s2.added is not None
    assert s2.monitored and s2.has_file


def test_season_size_is_sum_of_episode_files():
    by = {i.season: i for i in build_sonarr_items(FakeSonarr(), "season")}
    assert by[2].size_bytes == 500
    assert by[1].size_bytes == 100 and not by[1].monitored
    assert not by[3].has_file
    assert len(by[2].episodes) == 3 and by[2].episodes[2].file_id is None


def test_rank_from_latest_ignores_specials_and_unaired():
    seasons = build_sonarr_items(FakeSonarr(), "season")
    assert {i.season: i.rank_from_latest for i in seasons} == {1: 1, 2: 0, 3: None}
    eps = build_sonarr_items(FakeSonarr(), "episode")
    assert {(i.season, i.episode): i.rank_from_latest for i in eps} == {
        (1, 1): 3,
        (2, 1): 2,
        (2, 2): 1,
        (2, 3): 0,
        (3, 1): None,
        (3, 2): None,
    }
    (series,) = build_sonarr_items(FakeSonarr(), "series")
    assert series.rank_from_latest is None and len(series.episodes) == 6


def test_episode_keys_and_titles():
    eps = build_sonarr_items(FakeSonarr(), "episode")
    e = next(i for i in eps if (i.season, i.episode) == (2, 3))
    assert e.key == "sonarr:episode:10:2:3"
    assert e.title == "Breaking Bad – S02E03" and e.base_title == "Breaking Bad"
    s = build_sonarr_items(FakeSonarr(), "season")[1]
    assert (s.key, s.title) == ("sonarr:season:10:2", "Breaking Bad – S02")
    (ser,) = build_sonarr_items(FakeSonarr(), "series")
    assert (ser.key, ser.title) == ("sonarr:series:10", "Breaking Bad (2008)")


def test_unit_added_is_newest_file_date_with_series_fallback():
    series_added = datetime(2022, 5, 6, 7, 8, 9, tzinfo=UTC)
    by = {i.season: i for i in build_sonarr_items(FakeSonarr(), "season")}
    assert by[2].added == datetime(2023, 4, 1, tzinfo=UTC)  # newest of its files
    assert by[1].added == series_added  # file without dateAdded
    assert by[3].added == series_added  # no files at all
    eps = {(i.season, i.episode): i for i in build_sonarr_items(FakeSonarr(), "episode")}
    assert eps[2, 1].added == datetime(2023, 3, 1, tzinfo=UTC)
    assert eps[2, 3].added == series_added
    (ser,) = build_sonarr_items(FakeSonarr(), "series")
    assert ser.added == series_added
