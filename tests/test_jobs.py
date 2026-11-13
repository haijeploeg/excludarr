from datetime import datetime

from excludarr.config import Config
from excludarr.jobs import JobSpec, Planner, configured_jobs


def utc(value):
    return datetime.fromisoformat("2026-11-11T" + value + "+00:00")


def test_order_batch_coalescing_and_release():
    jobs = [
        JobSpec(("rule", "A"), "2 * * * *", 0),
        JobSpec(("rule", "B"), "0 * * * *", 1),
        JobSpec(("list", "movies"), "1 * * * *", 0),
    ]
    planner = Planner(jobs, "UTC", utc("09:59:00"), {})
    first = planner.take_batch(utc("10:37:00"))
    assert [j.key for j in first] == [("rule", "B")]
    planner.release(first)
    again = planner.take_batch(utc("10:50:00"))
    assert again == first
    planner.start(first[0].key)
    planner.complete(first[0].key, utc("10:51:00"))
    second = planner.take_batch(utc("10:51:00"))
    assert [j.key for j in second] == [("list", "movies")]
    planner.start(second[0].key)
    planner.complete(second[0].key, utc("10:52:00"))
    assert [j.key for j in planner.take_batch(utc("10:53:00"))] == [("rule", "A")]
    assert len(planner.snapshot()) == 3


def test_ties_file_order_and_no_active_backlog():
    jobs = [
        JobSpec(("rule", "B"), "* * * * *", 1),
        JobSpec(("rule", "A"), "* * * * *", 0),
        JobSpec(("list", "A"), "* * * * *", 0),
    ]
    planner = Planner(jobs, "UTC", utc("10:00:00"), {})
    feed = planner.take_batch(utc("10:01:00"))
    assert [j.key for j in feed] == [("list", "A")]
    planner.start(feed[0].key)
    planner.complete(feed[0].key, utc("10:01:30"))
    rules = planner.take_batch(utc("10:01:30"))
    assert [j.key for j in rules] == [("rule", "A"), ("rule", "B")]
    assert [s["state"] for s in planner.snapshot() if s["kind"] == "rule"] == ["pending", "pending"]
    planner.start(("rule", "A"))
    planner.poll(utc("10:20:00"))
    planner.complete(("rule", "A"), utc("10:20:00"))
    state = next(s for s in planner.snapshot() if s["name"] == "A" and s["kind"] == "rule")
    assert state["next_due"] == utc("10:21:00")


def test_restart_clock_rewind_and_manual_only():
    planner = Planner(
        [JobSpec(("rule", "A"), "0 * * * *", 0)],
        "UTC",
        utc("10:37:00"),
        {("rule", "A"): utc("12:00:00")},
    )
    assert planner.take_batch(utc("12:30:00")) == []
    assert planner.snapshot()[0]["next_due"] == utc("13:00:00")
    cfg = Config.model_validate(
        {
            "integrations": {"radarr": {"url": "http://r", "api_key": "k"}},
            "rules": [
                {
                    "name": name,
                    "target": "radarr",
                    "action": "tag",
                    "tag": "test",
                    "when": {"year": {"min": 2000}},
                    **kw,
                }
                for name, kw in [
                    ("manual", {}),
                    ("disabled", {"enabled": False, "schedule": "* * * * *"}),
                    ("scheduled", {"schedule": "0 2 * * *"}),
                ]
            ],
        }
    )
    assert [j.key for j in configured_jobs(cfg)] == [("rule", "scheduled")]
