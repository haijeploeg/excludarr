from datetime import UTC, datetime, timedelta

import pytest

from excludarr import engine
from excludarr.actions import ActionResult
from excludarr.clients.plex import PlexItem
from excludarr.config import Config
from excludarr.facts import Clients, Context
from excludarr.items import MediaItem
from excludarr.storage.repo import Repo

NOW = datetime(2026, 1, 1, tzinfo=UTC)


class FakePlex:
    def __init__(self):
        self.calls = []

    def add_to_collection(self, item, name):
        self.calls.append(("add", item.rating_key, name))

    def remove_from_collection(self, item, name):
        self.calls.append(("remove", item.rating_key, name))

    def season(self, show, number):
        return PlexItem(f"{show.rating_key}s{number}", show.section_key, "season")

    def episode(self, show, season, number):
        return PlexItem(f"{show.rating_key}s{season}e{number}", show.section_key, "episode")


def movie(mid, monitored=True, year=2000):
    return MediaItem(
        key=f"radarr:movie:{mid}", kind="movie", title=f"M{mid}", base_title=f"M{mid}",
        arr_id=mid, tmdb_id=mid, year=year, monitored=monitored, size_bytes=100,
    )  # fmt: skip


def season(sid, n, has_file=True):
    return MediaItem(
        key=f"sonarr:season:{sid}:{n}", kind="season", title=f"S{sid}-{n}", base_title=f"S{sid}",
        arr_id=sid, season=n, tvdb_id=sid, has_file=has_file,
    )  # fmt: skip


def episode(sid, s, e, has_file=True):
    return MediaItem(
        key=f"sonarr:episode:{sid}:{s}:{e}", kind="episode", title=f"S{sid}-{s}x{e}",
        base_title=f"S{sid}", arr_id=sid, season=s, episode=e, tvdb_id=sid, has_file=has_file,
    )  # fmt: skip


def series(sid):
    return MediaItem(
        key=f"sonarr:series:{sid}", kind="series", title=f"S{sid}", base_title=f"S{sid}",
        arr_id=sid, tvdb_id=sid,
    )  # fmt: skip


@pytest.fixture
def env(tmp_path, monkeypatch, minimal_cfg):
    """Returns make(rules, movies=..., seasons=..., series_=...) -> Context; records executions."""
    state = {"executed": [], "fail": set()}

    def fake_execute(rule, item, ctx):
        state["executed"].append((rule.name, item.key))
        if item.key in state["fail"]:
            return ActionResult(False, 0, "boom")
        return ActionResult(True, item.size_bytes, "done")

    monkeypatch.setattr(engine, "execute", fake_execute)
    repo = Repo(f"sqlite:///{tmp_path / 'db.sqlite'}")

    def make(rules, movies=(), seasons=(), series_=(), episodes=(), now=NOW):
        monkeypatch.setattr(engine, "build_radarr_items", lambda radarr: list(movies))
        monkeypatch.setattr(
            engine,
            "build_sonarr_items",
            lambda sonarr, level: list(
                {"series": series_, "season": seasons, "episode": episodes}[level]
            ),
        )
        cfg = Config.model_validate(
            {
                **minimal_cfg,
                "integrations": {
                    **minimal_cfg["integrations"],
                    "plex": {"url": "http://plex:32400", "token": "t"},
                },
                "rules": rules,
            }
        )
        plex = FakePlex()
        ctx = Context(cfg, Clients(radarr=object(), sonarr=object(), plex=plex), repo, now)
        # Sonarr items resolve to their parent show in Plex.
        ctx.plex_item = lambda item: PlexItem(
            f"show{item.arr_id}" if item.kind != "movie" else item.key, "1", "movie"
        )
        state["plex"] = plex
        return ctx

    state["make"] = make
    state["repo"] = repo
    return state


def rule(name="r", **kw):
    return {
        "name": name,
        "target": "radarr",
        "action": "delete",
        "preview": False,
        "when": {"monitored": True},
        **kw,
    }


def test_preview_progress_covers_loading_and_all_items_including_exceptions(env):
    ctx = env["make"]([rule()], movies=[movie(1), movie(2)])
    ctx.repo.exception_add("r", "radarr:movie:2", "M2")
    events = []
    [report] = engine.run(ctx, dry_run=True, progress=lambda *event: events.append(event))
    assert events[0] == ("Loading Radarr library", 0, None)
    assert [(done, total) for _, done, total in events[1:]] == [(0, 2), (1, 2), (2, 2)]
    assert [match.item.key for match in report.matches] == ["radarr:movie:1"]
    assert env["executed"] == []


def test_preview_rule_changes_nothing(env):
    ctx = env["make"]([rule(preview=True, grace_period="14d")], movies=[movie(1)])
    [report] = engine.run(ctx, dry_run=False)
    assert [m.item.key for m in report.matches] == ["radarr:movie:1"]
    assert env["executed"] == [] and env["repo"].queue_all() == []
    assert report.queued == [] and env["plex"].calls == []
    # dry_run on a live rule is just as inert
    ctx = env["make"]([rule()], movies=[movie(1)])
    engine.run(ctx, dry_run=True)
    assert env["executed"] == [] and env["repo"].history() == []


@pytest.mark.parametrize("protected", [False, True])
def test_preview_plans_queue_dates_without_mutating_state(env, protected):
    ctx = env["make"](
        [rule(grace_period="14d", preview=protected)], movies=[movie(1), movie(2), movie(3)]
    )
    ctx.repo.queue_add("r", "radarr:movie:2", "M2", 100, NOW - timedelta(hours=1))
    ctx.repo.queue_add("r", "radarr:movie:3", "M3", 100, NOW + timedelta(days=2))
    before = {key: row.due_at for key, row in ctx.repo.queue_for("r").items()}
    [report] = engine.run(ctx, dry_run=True)
    assert [(m.next_step, m.due_at) for m in report.matches] == [
        ("queue", NOW + timedelta(days=14)),
        ("execute", NOW - timedelta(hours=1)),
        ("wait", NOW + timedelta(days=2)),
    ]
    assert {key: row.due_at for key, row in ctx.repo.queue_for("r").items()} == before
    assert ctx.repo.history() == [] and env["executed"] == []


def test_preview_marks_later_removal_match_skipped_and_counts_space_once(env):
    from excludarr.preview import estimated_savings

    item = movie(1)
    item.has_file = True
    ctx = env["make"](
        [
            rule("first", action="delete_files"),
            rule("second", delete_files=True),
        ],
        movies=[item],
    )
    reports = engine.run(ctx, dry_run=True)
    assert [report.matches[0].next_step for report in reports] == ["execute", "skip"]
    assert estimated_savings(reports) == (1, 100, 0)
    assert env["executed"] == []


def test_preview_command_simulates_protected_rules_without_actions_or_prompts(env):
    from excludarr.preview import estimated_savings

    item = movie(1)
    item.has_file = True
    ctx = env["make"](
        [
            rule("first", preview=True, action="delete_files"),
            rule("second", action="delete_files"),
        ],
        movies=[item],
    )

    def unexpected_prompt(matches):
        raise AssertionError("Preview must not prompt")

    reports = engine.run(ctx, dry_run=True, confirm=unexpected_prompt, select=unexpected_prompt)
    assert [report.matches[0].next_step for report in reports] == ["execute", "skip"]
    assert estimated_savings(reports) == (1, 100, 0)
    assert ctx.repo.queue_all() == [] and ctx.repo.history() == [] and env["executed"] == []
    assert ctx.config.rules[0].preview is True

    # The protection remains effective when using run.
    reports = engine.run(ctx, dry_run=False)
    assert reports[0].matches[0].next_step == "preview"
    assert reports[0].executed == []
    assert len(reports[1].executed) == 1


def test_grace_enqueues_then_executes_when_due(env):
    rules = [rule(grace_period="14d", leaving_soon_collection=True)]
    ctx = env["make"](rules, movies=[movie(1)])
    [report] = engine.run(ctx, dry_run=False)
    assert [(m.item.key, due) for m, due in report.queued] == [
        ("radarr:movie:1", NOW + timedelta(days=14))
    ]
    assert env["executed"] == []
    assert env["plex"].calls == [("add", "radarr:movie:1", "Leaving Soon")]

    ctx = env["make"](rules, movies=[movie(1)], now=NOW + timedelta(days=13))
    [report] = engine.run(ctx, dry_run=False)
    assert [m.item.key for m, _ in report.pending] == ["radarr:movie:1"]
    assert env["executed"] == [] and report.queued == []

    ctx = env["make"](rules, movies=[movie(1)], now=NOW + timedelta(days=14))
    [report] = engine.run(ctx, dry_run=False)
    assert env["executed"] == [("r", "radarr:movie:1")]
    assert [r.ok for _, r in report.executed] == [True]
    assert env["repo"].queue_all() == []
    assert env["plex"].calls == [("remove", "radarr:movie:1", "Leaving Soon")]
    [h] = env["repo"].history()
    assert (h.rule, h.item_key, h.action, h.ok, h.size_freed) == (
        "r",
        "radarr:movie:1",
        "delete",
        True,
        100,
    )


def test_queued_item_no_longer_matching_is_dropped(env):
    rules = [rule(grace_period="7d", leaving_soon_collection=True)]
    engine.run(env["make"](rules, movies=[movie(1)]), dry_run=False)
    ctx = env["make"](rules, movies=[movie(1, monitored=False)], now=NOW + timedelta(days=8))
    [report] = engine.run(ctx, dry_run=False)
    assert report.dropped == ["M1"]
    assert env["executed"] == [] and env["repo"].queue_all() == []
    assert env["plex"].calls == [("remove", "radarr:movie:1", "Leaving Soon")]


def test_exception_skips_item(env):
    env["repo"].exception_add("r", "radarr:movie:1", "M1")
    ctx = env["make"]([rule()], movies=[movie(1), movie(2)])
    [report] = engine.run(ctx, dry_run=False)
    assert [m.item.key for m in report.matches] == ["radarr:movie:2"]
    assert env["executed"] == [("r", "radarr:movie:2")]


def test_failed_execution_stays_queued(env):
    env["fail"].add("radarr:movie:1")
    rules = [rule(grace_period="1d", leaving_soon_collection=True)]
    engine.run(env["make"](rules, movies=[movie(1)]), dry_run=False)
    ctx = env["make"](rules, movies=[movie(1)], now=NOW + timedelta(days=2))
    [report] = engine.run(ctx, dry_run=False)
    assert [r.ok for _, r in report.executed] == [False]
    assert [q.item_key for q in env["repo"].queue_all()] == ["radarr:movie:1"]
    assert ("remove", "radarr:movie:1", "Leaving Soon") not in env["plex"].calls
    assert env["repo"].history()[0].ok is False


def test_orphaned_queue_rows_dropped(env):
    due = NOW + timedelta(days=3)
    repo = env["repo"]
    repo.queue_add("gone", "sonarr:season:5:1", "S5-1", 0, due)
    repo.queue_add("gone", "sonarr:season:5:2", "S5-2", 0, due)
    repo.queue_add("kept", "sonarr:season:5:3", "S5-3", 0, due)
    kept = rule("kept", target="sonarr", preview=True, when={"monitored": False})
    ctx = env["make"]([kept], seasons=[season(5, 1), season(5, 2), season(5, 3)])
    engine.run(ctx, dry_run=False)
    assert [q.rule for q in repo.queue_all()] == ["kept"]
    # Each season leaves on its own; season 3 is still queued and stays.
    assert env["plex"].calls == [
        ("remove", "show5s1", "Leaving Soon"),
        ("remove", "show5s2", "Leaving Soon"),
    ]

    env["plex"].calls.clear()
    repo.queue_add("gone", "sonarr:season:5:3", "S5-3", 0, due)
    engine.run(ctx, dry_run=False)
    # The "kept" row still covers season 3, so it stays in the collection.
    assert [q.rule for q in repo.queue_all()] == ["kept"]
    assert env["plex"].calls == []


def test_collection_holds_seasons_not_the_show(env):
    rules = [rule(target="sonarr", grace_period="7d", leaving_soon_collection=True)]
    seasons = [season(5, 1), season(5, 2)]
    engine.run(env["make"](rules, seasons=seasons), dry_run=False)
    assert env["plex"].calls == [
        ("add", "show5s1", "Leaving Soon"),
        ("add", "show5s2", "Leaving Soon"),
    ]

    env["plex"].calls.clear()
    seasons[1].monitored = False
    [report] = engine.run(env["make"](rules, seasons=seasons), dry_run=False)
    assert report.dropped == ["S5-2"]
    assert env["plex"].calls == [("remove", "show5s2", "Leaving Soon")]


def test_collection_holds_episodes_not_the_show(env):
    rules = [
        rule(target="sonarr", level="episode", grace_period="7d", leaving_soon_collection=True)
    ]
    engine.run(env["make"](rules, episodes=[episode(5, 1, 2)]), dry_run=False)
    assert env["plex"].calls == [("add", "show5s1e2", "Leaving Soon")]


def test_later_rule_skips_removed_items(env):
    rules = [
        rule("series", target="sonarr", level="series"),
        rule("seasons", target="sonarr"),
        rule("movies-a"),
        rule("movies-b"),
    ]
    ctx = env["make"](
        rules, movies=[movie(1)], seasons=[season(5, 1), season(6, 1)], series_=[series(5)]
    )
    reports = engine.run(ctx, dry_run=False)
    assert [m.item.key for m in reports[1].matches] == ["sonarr:season:6:1"]
    assert reports[3].matches == []
    assert env["executed"] == [
        ("series", "sonarr:series:5"),
        ("seasons", "sonarr:season:6:1"),
        ("movies-a", "radarr:movie:1"),
    ]


def test_condition_counts_include_unknown(env):
    r = rule(when={"any": [{"monitored": True}, {"year": {"min": 2010}}]}, preview=True)
    ctx = env["make"](
        [r], movies=[movie(1), movie(2, monitored=False, year=None), movie(3, year=2020)]
    )
    [report] = engine.run(ctx, dry_run=False)
    assert report.condition_counts == {"monitored": (2, 0), "year min 2010": (1, 1)}
    by_key = {m.item.key: m.reasons for m in report.matches}
    assert by_key == {
        "radarr:movie:1": ["monitored"],
        "radarr:movie:3": ["monitored", "year min 2010"],
    }


def test_unknown_unless_never_acts(env):
    r = rule(unless=[{"year": {"min": 2010}}], preview=True)
    ctx = env["make"]([r], movies=[movie(1, year=None), movie(2, year=2000)])
    [report] = engine.run(ctx, dry_run=False)
    assert [m.item.key for m in report.matches] == ["radarr:movie:2"]


def test_confirm_false_executes_nothing(env):
    ctx = env["make"]([rule()], movies=[movie(1)])
    seen = []
    [report] = engine.run(ctx, dry_run=False, confirm=lambda m: seen.append(m) or False)
    assert [m.item.key for m in seen[0]] == ["radarr:movie:1"]
    assert env["executed"] == [] and report.executed == []
    # Due grace items are not executed either and stay queued.
    rules = [rule(grace_period="1d")]
    engine.run(env["make"](rules, movies=[movie(1)]), dry_run=False)
    ctx = env["make"](rules, movies=[movie(1)], now=NOW + timedelta(days=2))
    engine.run(ctx, dry_run=False, confirm=lambda m: False)
    assert env["executed"] == [] and len(env["repo"].queue_all()) == 1


def test_select_limits_matches(env):
    ctx = env["make"]([rule()], movies=[movie(1), movie(2)])
    engine.run(ctx, dry_run=False, select=lambda rep: rep.matches[1:])
    assert env["executed"] == [("r", "radarr:movie:2")]


def test_grace_switched_to_zero_drops_rows(env):
    engine.run(env["make"]([rule(grace_period="7d", leaving_soon_collection=True)],
                           movies=[movie(1)]), dry_run=False)  # fmt: skip
    ctx = env["make"]([rule()], movies=[movie(1, monitored=False)])
    [report] = engine.run(ctx, dry_run=False)
    assert report.dropped == ["M1"] and env["repo"].queue_all() == []
    assert env["plex"].calls == [("remove", "radarr:movie:1", "Leaving Soon")]


def test_collection_flag_off_still_uncollects(env):
    rules = [rule(grace_period="1d", leaving_soon_collection=True)]
    engine.run(env["make"](rules, movies=[movie(1), movie(2)]), dry_run=False)
    off = [rule(grace_period="1d")]
    ctx = env["make"](
        off, movies=[movie(1), movie(2, monitored=False)], now=NOW + timedelta(days=2)
    )
    [report] = engine.run(ctx, dry_run=False)
    assert report.dropped == ["M2"] and env["executed"] == [("r", "radarr:movie:1")]
    assert sorted(c for c in env["plex"].calls if c[0] == "remove") == [
        ("remove", "radarr:movie:1", "Leaving Soon"),
        ("remove", "radarr:movie:2", "Leaving Soon"),
    ]


@pytest.mark.parametrize(
    "extra",
    [{"when": {"year": {"min": 1990}}}, {"unless": [{"year": {"min": 2010}}]}],
    ids=["when-unknown", "unless-unknown"],
)
def test_queued_unknown_stays_pending(env, extra):
    rules = [rule(grace_period="1d", leaving_soon_collection=True)]
    engine.run(env["make"](rules, movies=[movie(1)]), dry_run=False)
    later = [rule(grace_period="1d", leaving_soon_collection=True, **extra)]
    ctx = env["make"](later, movies=[movie(1, year=None)], now=NOW + timedelta(days=2))
    [report] = engine.run(ctx, dry_run=False)
    assert [m.item.key for m, _ in report.pending] == ["radarr:movie:1"]
    assert report.dropped == [] and report.matches == [] and env["executed"] == []
    assert [q.item_key for q in env["repo"].queue_all()] == ["radarr:movie:1"]
    assert env["plex"].calls == []  # not uncollected


def test_episode_rule_skips_removed_season(env):
    rules = [rule("seasons", target="sonarr"), rule("eps", target="sonarr", level="episode")]
    ctx = env["make"](rules, seasons=[season(5, 1)], episodes=[episode(5, 1, 1), episode(5, 2, 1)])
    reports = engine.run(ctx, dry_run=False)
    assert [m.item.key for m in reports[1].matches] == ["sonarr:episode:5:2:1"]


@pytest.mark.parametrize("action", ["delete", "delete_files"])
def test_delete_skips_empty_units(env, action):
    rules = [
        rule("seasons", target="sonarr", action=action),
        rule("eps", target="sonarr", level="episode", action=action),
        rule("unmon", target="sonarr", action="unmonitor"),
    ]
    ctx = env["make"](
        rules,
        seasons=[season(5, 1), season(6, 1, has_file=False)],
        episodes=[episode(7, 1, 1, has_file=False), episode(7, 1, 2)],
    )
    reports = engine.run(ctx, dry_run=True)
    assert [m.item.key for m in reports[0].matches] == ["sonarr:season:5:1"]
    assert [m.item.key for m in reports[1].matches] == ["sonarr:episode:7:1:2"]
    # Other actions still match empty units.
    assert len(reports[2].matches) == 2


def test_preflight_unknown_provider_in_second_rule_acts_on_nothing(env, monkeypatch):
    from excludarr.clients.justwatch import Provider
    from excludarr.config import ConfigError

    rules = [
        rule("first"),
        rule("second", when={"streaming": {"providers": ["Nope"]}}),
    ]
    ctx = env["make"](rules, movies=[movie(1)])
    calls = []

    def providers():
        calls.append(1)
        return [Provider(8, "Netflix", "nfx", [])]

    ctx._providers = providers
    ctx.clients.justwatch = type("JW", (), {"locale": "en_US"})()
    with pytest.raises(ConfigError, match="unknown provider 'Nope'"):
        engine.run(ctx, dry_run=False)
    assert env["executed"] == []
    # provider_ids is memoized per run
    assert ctx.provider_ids(["Netflix"]) == ctx.provider_ids(["Netflix"]) == {8}
    assert len(calls) == 1  # both name lookups use the same provider catalogue


def test_preflight_builds_all_item_sets_before_acting(env, monkeypatch):
    rules = [rule("first"), rule("second", target="sonarr")]
    ctx = env["make"](rules, movies=[movie(1)])

    def boom(sonarr, level):
        raise RuntimeError("sonarr down")

    monkeypatch.setattr(engine, "build_sonarr_items", boom)
    with pytest.raises(RuntimeError):
        engine.run(ctx, dry_run=False)
    assert env["executed"] == []


def test_due_subset_keeps_order_shared_removals_and_other_queue(env):
    ctx = env["make"]([rule("A"), rule("B"), rule("manual")], movies=[movie(1)])
    ctx.repo.queue_add("manual", "radarr:movie:1", "M1", 100, NOW)
    completed = []
    reports = engine.run(
        ctx,
        dry_run=False,
        rule_names=frozenset({"B", "A"}),
        on_rule_complete=lambda r: completed.append(r.rule.name),
    )
    assert [r.rule.name for r in reports] == ["A", "B"]
    assert completed == ["A", "B"]
    assert env["executed"] == [("A", "radarr:movie:1")]
    assert len(ctx.repo.queue_for("manual")) == 1


def test_stop_between_rules_and_before_first(env):
    ctx = env["make"]([rule("A", preview=True), rule("B")], movies=[movie(1)])
    completed = []
    reports = engine.run(
        ctx,
        dry_run=False,
        should_stop=lambda: bool(completed),
        on_rule_complete=lambda r: completed.append(r.rule.name),
    )
    assert [r.rule.name for r in reports] == ["A"]
    assert env["executed"] == []
    assert engine.run(ctx, dry_run=False, should_stop=lambda: True) == []


def test_rule_lifecycle_retains_completed_before_exception(env):
    ctx = env["make"]([rule("A", preview=True), rule("B"), rule("C")], movies=[movie(1)])
    starts, completed = [], []

    def start(rule):
        starts.append(rule.name)
        if rule.name == "B":
            raise RuntimeError("failure in B")

    with pytest.raises(RuntimeError, match="failure in B"):
        engine.run(
            ctx,
            dry_run=False,
            on_rule_start=start,
            on_rule_complete=lambda r: completed.append(r.rule.name),
        )
    assert starts == ["A", "B"]
    assert completed == ["A"]
