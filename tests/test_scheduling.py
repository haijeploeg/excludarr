from datetime import datetime

import pytest
from pydantic import ValidationError

from excludarr.config import Config
from excludarr.lists.service import fingerprint
from excludarr.scheduling import SchedulerConfig, next_occurrence, validate_schedule


def utc(value):
    return datetime.fromisoformat(value)


@pytest.mark.parametrize(
    "expression", ["*/5 * * * *", "0 2 * * MON-FRI", "0 0 1 JAN,JUN *", "0 0 * * 0", "0 0 * * 7"]
)
def test_standard_cron(expression):
    assert validate_schedule(expression) == expression


@pytest.mark.parametrize(
    "expression",
    [
        True,
        5,
        [],
        "0 0 30 2 *",
        "@reboot",
        "0 0 * * * *",
        "0 0 * * * 2026",
        "0 0 L * *",
        "0 0 1W * *",
        "0 0 * * MON#2",
        "H * * * *",
        "R * * * *",
        "0 0 ? * *",
        "60 * * * *",
    ],
)
def test_invalid_cron(expression):
    with pytest.raises(ValueError):
        validate_schedule(expression)


@pytest.mark.parametrize(
    "expression,after,expected",
    [
        ("0 2 * * *", "2026-11-11T00:00:00Z", "2026-11-11T01:00:00Z"),
        ("30 2 * * *", "2026-03-29T00:00:00Z", "2026-03-30T00:30:00Z"),
        ("30 2 * * *", "2026-10-25T00:00:00Z", "2026-10-25T00:30:00Z"),
        ("30 2 * * *", "2026-10-25T00:45:00Z", "2026-10-26T01:30:00Z"),
        ("30 2 * * *", "2026-10-25T01:15:00Z", "2026-10-26T01:30:00Z"),
        ("0 0 1 * MON", "2026-11-02T00:00:00Z", "2026-11-08T23:00:00Z"),
    ],
)
def test_local_occurrences(expression, after, expected):
    assert next_occurrence(expression, utc(after), "Europe/Amsterdam") == utc(expected)


def test_timezone_and_schedule_defaults():
    assert SchedulerConfig().timezone == "UTC"
    with pytest.raises(ValidationError):
        SchedulerConfig(timezone="Not/AZone")


def test_existing_feed_fingerprint_survives_scheduling():
    config = Config.model_validate(
        {
            "integrations": {"radarr": {"url": "http://r", "api_key": "arr-secret"}},
            "list_proxy": {
                "api_key": "feed-secret",
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
    original = "cd4b9f32f9452d6d5be075c4a573a5c3edc5106120760b4a59f2d0c7ac26195f"
    assert config.list_proxy.lists["movies"].schedule is None
    assert fingerprint(config, "movies") == original
    config.list_proxy.lists["movies"].schedule = "0 * * * *"
    config.scheduler.timezone = "Europe/Amsterdam"
    assert fingerprint(config, "movies") == original


@pytest.mark.parametrize("schedule,warns", [("0 * * * *", False), ("0 */6 * * *", True)])
def test_feed_expiry_warning_keeps_valid_config(schedule, warns):
    from excludarr.scheduling import schedule_warnings

    config = Config.model_validate(
        {
            "integrations": {"radarr": {"url": "http://r", "api_key": "k"}},
            "list_proxy": {
                "api_key": "test-key",
                "sources": {"s": {"type": "stevenlu"}},
                "lists": {
                    "movies": {
                        "target": "radarr",
                        "sources": ["s"],
                        "schedule": schedule,
                        "when": {"year": {"min": 2000}},
                    }
                },
            },
        }
    )
    warnings = schedule_warnings(config, utc("2026-11-11T00:00:00Z"))
    assert bool(warnings) is warns
    if warns:
        assert "six hours" in warnings[0]
