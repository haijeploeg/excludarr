from dataclasses import replace

import pytest

from excludarr.config import Rule
from excludarr.engine import Match, RuleReport
from excludarr.items import MediaItem
from excludarr.preview import action_description, estimated_savings


def make_rule(**kwargs):
    return Rule(name="r", target="radarr", when={"monitored": True}, action="delete", **kwargs)


@pytest.mark.parametrize(
    ("action", "options", "expected"),
    [
        ("delete", {}, "Remove from Radarr; keep files"),
        (
            "delete",
            {"delete_files": True, "import_exclusion": True},
            "Remove from Radarr and delete files; add import exclusion",
        ),
        ("delete_files", {}, "Delete files and disable monitoring"),
        ("monitor", {"search": True}, "Enable monitoring; search for missing media"),
        ("unmonitor", {}, "Disable monitoring"),
        ("tag", {"tag": "keep"}, "Add tag 'keep'"),
        ("import_exclusion", {}, "Add import exclusion"),
    ],
)
def test_action_description_includes_effective_flags(action, options, expected):
    rule = Rule(name="r", target="radarr", action=action, when={"monitored": True}, **options)
    assert action_description(rule) == expected


def test_season_delete_describes_files_and_ignores_inapplicable_import_flag():
    rule = Rule(
        name="r",
        target="sonarr",
        action="delete",
        import_exclusion=True,
        when={"monitored": True},
    )
    assert action_description(rule) == "Delete files and disable monitoring"


def test_estimates_deduplicate_files_across_rules_and_prioritize_next_run():
    rule = make_rule(delete_files=True)
    movie = MediaItem("radarr:movie:1", "movie", "Movie", "Movie", 1, has_file=True, size_bytes=100)
    series = MediaItem(
        "sonarr:series:1",
        "series",
        "Show",
        "Show",
        1,
        has_file=True,
        size_bytes=300,
        file_sizes={10: 100, 11: 200},
    )
    season = replace(
        series,
        key="sonarr:season:1:1",
        kind="season",
        season=1,
        file_sizes={10: 100},
        size_bytes=100,
    )
    tv_rule = Rule(name="tv", target="sonarr", action="delete_files", when={"monitored": True})
    reports = [
        RuleReport(
            rule,
            [
                Match(rule, movie, [], next_step="execute"),
                Match(rule, movie, [], next_step="queue"),
                Match(rule, replace(movie, arr_id=2), [], next_step="preview"),
            ],
            {},
        ),
        RuleReport(
            tv_rule,
            [
                Match(tv_rule, season, [], next_step="execute"),
                Match(tv_rule, series, [], next_step="wait"),
            ],
            {},
        ),
    ]
    assert estimated_savings(reports) == (3, 200, 200)


@pytest.mark.parametrize("step", ["execute", "queue"])
def test_keep_files_and_monitor_actions_have_zero_reclaimable_space(step):
    movie = MediaItem("radarr:movie:1", "movie", "Movie", "Movie", 1, has_file=True, size_bytes=100)
    for action in ("delete", "monitor", "unmonitor", "tag", "import_exclusion"):
        rule = Rule(name="r", target="radarr", action=action, tag="keep", when={"monitored": True})
        report = RuleReport(rule, [Match(rule, movie, [], next_step=step)], {})
        assert estimated_savings([report]) == (1, 0, 0)
