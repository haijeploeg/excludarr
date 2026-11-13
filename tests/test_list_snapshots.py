from datetime import UTC, datetime, timedelta

from excludarr.config import Config
from excludarr.lists.service import fingerprint, snapshot_valid
from excludarr.storage.repo import Repo


def config(key="feed-secret"):
    return Config.model_validate(
        {
            "integrations": {"radarr": {"url": "http://r", "api_key": "arr-secret"}},
            "list_proxy": {
                "api_key": key,
                "sources": {"s": {"type": "stevenlu"}},
                "lists": {
                    "movies": {
                        "target": "radarr",
                        "sources": ["s"],
                        "when": {"year": {"min": 2000}},
                    }
                },
            },
        }
    )


def test_publish_failure_and_expiry(tmp_path):
    repo = Repo(f"sqlite:///{tmp_path}/db")
    now = datetime.now(UTC)
    fp = fingerprint(config(), "movies")
    repo.list_publish("movies", [{"imdb_id": "tt1"}], {"items": []}, fp, now)
    repo.list_failure("movies", "source failed", now + timedelta(hours=1))
    snap = repo.list_snapshot("movies")
    assert snap.payload == [{"imdb_id": "tt1"}]
    assert snap.successful_at == now
    assert snap.last_error == "source failed"
    assert snapshot_valid(snap, fp, now + timedelta(hours=5))
    assert not snapshot_valid(snap, fp, now + timedelta(hours=6))
    assert not snapshot_valid(snap, fp, now - timedelta(seconds=1))
    assert not snapshot_valid(snap, "different", now)
    repo.list_publish("movies", [], {}, fp, now)
    assert repo.list_snapshot("movies").last_error is None


def test_first_failure_and_fingerprint(tmp_path):
    repo = Repo(f"sqlite:///{tmp_path}/db")
    now = datetime.now(UTC)
    repo.list_failure("movies", "failed", now)
    assert repo.list_snapshot("movies").successful_at is None
    assert not snapshot_valid(repo.list_snapshot("movies"), "fp", now)
    fp = fingerprint(config(), "movies")
    assert fp == fingerprint(config(), "movies")
    assert fp != fingerprint(config("rotated"), "movies")
    changed = config()
    changed.list_proxy.lists["movies"].when.params = (2021, None)
    assert fp != fingerprint(changed, "movies")
    assert "secret" not in fp


def test_quality_changes_snapshot_fingerprint(tmp_path):
    from excludarr.conditions import parse_condition

    cfg = config()
    repo = Repo(f"sqlite:///{tmp_path}/quality.db")
    now = datetime.now(UTC)
    hashes = []
    for minimum in (None, "hd", "4k"):
        params = {"providers": ["Netflix"]}
        if minimum:
            params["min_quality"] = minimum
        cfg.list_proxy.lists["movies"].when = parse_condition({"streaming": params})
        hashes.append(fingerprint(cfg, "movies"))
    assert len(set(hashes)) == 3
    repo.list_publish("movies", [], {}, hashes[1], now)
    assert not snapshot_valid(repo.list_snapshot("movies"), hashes[2], now)
