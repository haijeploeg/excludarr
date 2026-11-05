from datetime import UTC, datetime, timedelta

import pytest

from excludarr.storage.repo import Repo


@pytest.fixture
def repo(tmp_path):
    return Repo(f"sqlite:///{tmp_path}/t.db")


def test_queue_roundtrip(repo):
    due = datetime(2030, 1, 1, tzinfo=UTC)
    repo.queue_add("r1", "tmdb:1", "Movie", 100, due)
    repo.queue_add("r2", "tmdb:2", "Other", 5, due)
    e = repo.queue_for("r1")["tmdb:1"]
    assert (e.title, e.size_bytes, e.due_at) == ("Movie", 100, due)
    assert e.enqueued_at.tzinfo is not None
    assert len(repo.queue_all()) == 2
    repo.queue_remove("r1", "tmdb:1")
    assert repo.queue_for("r1") == {}
    assert len(repo.queue_all()) == 1


def test_exceptions(repo):
    repo.exception_add("r1", "tmdb:1", "Movie")
    repo.exception_add("r1", "tmdb:1", "Movie")  # idempotent
    repo.exception_add("r2", "tmdb:2", "Other")
    assert repo.exceptions_for("r1") == {"tmdb:1"}
    assert len(repo.exceptions_all()) == 2
    repo.exception_remove("r1", "tmdb:1")
    assert repo.exceptions_for("r1") == set()


def test_history_newest_first(repo):
    for i in range(3):
        repo.history_add("r", f"k{i}", "T", "delete", i, True, "")
    assert [h.item_key for h in repo.history()] == ["k2", "k1", "k0"]
    assert len(repo.history(limit=2)) == 2
    assert repo.history()[0].ok is True
    assert repo.history()[0].at.tzinfo is not None


def test_cache_roundtrip(repo):
    repo.cache_set("k", {"a": [1, 2]}, ttl=timedelta(hours=1))
    assert repo.cache_get("k") == {"a": [1, 2]}
    assert repo.cache_get("missing") is None


def test_cache_expiry(repo):
    repo.cache_set("k", {"a": 1}, ttl=timedelta(seconds=-1))
    assert repo.cache_get("k") is None


def test_migrations_idempotent(tmp_path):
    url = f"sqlite:///{tmp_path}/t.db"
    Repo(url).exception_add("r", "k", "T")
    assert Repo(url).exceptions_for("r") == {"k"}
