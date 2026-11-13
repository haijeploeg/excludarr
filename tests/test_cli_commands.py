import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from io import StringIO

import pytest
import yaml
from rich.console import Console
from rich.text import Text
from typer.testing import CliRunner

from excludarr import cli
from excludarr.actions import ActionResult
from excludarr.facts import Clients
from excludarr.items import MediaItem
from excludarr.storage.repo import Repo

GB = 1024**3


def movie(mid, title, size_gb, added_day=1):
    return MediaItem(
        key=f"radarr:movie:{mid}", kind="movie", title=title, base_title=title, arr_id=mid,
        tmdb_id=mid, size_bytes=size_gb * GB, monitored=True,
        added=datetime(2020, 1, added_day, tzinfo=UTC),
    )  # fmt: skip


MOVIES = [movie(1, "Bravo", 5), movie(2, "Alpha", 2), movie(3, "Charlie", 1)]


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = tmp_path / "db.sqlite"
    path = tmp_path / "c.yml"

    def write(rules=None, **extra):
        cfg = {
            "integrations": {"radarr": {"url": "http://r:7878", "api_key": "k"}},
            "database": f"sqlite:///{db}",
            "rules": rules
            or [
                {
                    "name": "r",
                    "target": "radarr",
                    "action": "delete",
                    "preview": False,
                    "when": {"monitored": True},
                }
            ],
            **extra,
        }
        path.write_text(yaml.safe_dump(cfg))

    write()
    monkeypatch.setattr(Clients, "from_config", classmethod(lambda cls, c: cls(radarr=object())))
    monkeypatch.setattr("excludarr.engine.build_radarr_items", lambda r: list(MOVIES))
    executed = []

    def fake_execute(rule, item, ctx):
        executed.append(item.key)
        return ActionResult(True, item.size_bytes, "done")

    monkeypatch.setattr("excludarr.engine.execute", fake_execute)

    def invoke(*args, input=None):
        return CliRunner().invoke(cli.app, ["--config", str(path), *args], input=input)

    return {
        "path": path,
        "invoke": invoke,
        "write": write,
        "repo": Repo(f"sqlite:///{db}"),
        "executed": executed,
    }


def test_preview_shows_overview_before_titles_and_per_item_evidence(env):
    r = env["invoke"]("preview")
    assert r.exit_code == 0, r.output
    assert "Preview" in r.output
    assert r.output.index("8.00 GB") < r.output.index("Bravo")
    assert r.output.count("monitored") == 3
    assert env["executed"] == []


def test_preview_with_rule_hides_diagnostic_counts_unless_debug(env):
    env["write"](
        [
            {
                "name": "r",
                "target": "radarr",
                "action": "delete",
                "when": {"year": {"min": 2020}},
            }
        ]
    )
    r = env["invoke"]("preview", "--rule", "r")
    assert r.exit_code == 0, r.output
    assert "0 unique titles" in r.output
    assert "Unknown" not in r.output and "3 unknown" not in r.output

    debug = env["invoke"]("--debug", "preview", "--rule", "r")
    assert debug.exit_code == 0, debug.output
    assert "Unknown" in debug.output and "year min 2020 (0 matched, 3 unknown)" in debug.output


def test_debug_preview_breaks_down_unknown_requester_watch_results(env, monkeypatch):
    from types import SimpleNamespace

    from excludarr.clients.seerr import SeerrRequest

    env["write"](
        [
            {
                "name": "Watched requests",
                "target": "radarr",
                "action": "delete",
                "when": {"requester_watched_more_than": "30d"},
            }
        ],
        integrations={
            "radarr": {"url": "http://r", "api_key": "k"},
            "seerr": {"url": "http://s", "api_key": "k"},
            "plex": {"url": "http://p", "token": "t"},
            "tautulli": {"url": "http://t", "api_key": "k"},
        },
    )
    clients = Clients(
        radarr=object(),
        plex=SimpleNamespace(items_by_guid=dict),
        tautulli=SimpleNamespace(history=list),
        seerr=SimpleNamespace(
            requests=lambda: [
                SeerrRequest(
                    i, i, "movie", i, None, datetime.now(UTC), frozenset({"viewer"}), frozenset()
                )
                for i in (2, 3)
            ]
        ),
    )
    monkeypatch.setattr(Clients, "from_config", classmethod(lambda cls, cfg: clients))
    result = env["invoke"]("--debug", "preview", "--rule", "Watched requests")
    assert result.exit_code == 0, result.output
    assert "1 Not requested" in result.output
    assert "2 Watch history unavailable" in result.output


def test_preview_simulates_savings_for_a_preview_only_rule(env, monkeypatch):
    env["write"](
        [
            {
                "name": "protected",
                "target": "radarr",
                "action": "delete_files",
                "preview": True,
                "when": {"monitored": True},
            }
        ]
    )
    monkeypatch.setattr(
        "excludarr.engine.build_radarr_items",
        lambda client: [replace(MOVIES[0], has_file=True)],
    )
    sink = StringIO()
    monkeypatch.setattr(cli, "Console", lambda: Console(file=sink, width=160))
    result = env["invoke"]("preview")
    assert result.exit_code == 0, result.output
    output = sink.getvalue()
    assert "Estimated space freed on execution 5.00 GB" in output
    assert "Would execute" in output and "Preview only" not in output
    assert "No actions will be executed" in output
    assert "excludarr run" in output and "set preview: false for: protected" in output
    assert env["executed"] == [] and env["repo"].queue_all() == []
    assert env["repo"].history() == []


@pytest.mark.parametrize("command", ["run", "preview"])
def test_fast_progress_keeps_completed_counts_for_each_rule(env, monkeypatch, command):
    import re

    sink = StringIO()
    monkeypatch.setattr(cli, "Console", lambda: Console(file=sink, force_terminal=True, width=100))
    names = ("first", "second rule with a longer name")
    env["write"](
        [
            {"name": name, "target": "radarr", "action": "delete", "when": {"monitored": True}}
            for name in names
        ]
    )
    result = env["invoke"](command)
    assert result.exit_code == 0, result.output
    assert "Evaluating" not in sink.getvalue()
    sink.seek(0)
    sink.truncate()
    result = env["invoke"](command, "--progress")
    assert result.exit_code == 0, result.output
    rendered = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", sink.getvalue())
    for name in names:
        assert re.search(rf"✓ Evaluating {name} +3/3", rendered)
    elapsed = list(
        re.finditer(
            r"✓ (?:Loading Radarr library|Evaluating first|Evaluating second rule with a longer name) +(?:3/3 +)?(\d+:\d{2}:\d{2})",
            rendered,
        )
    )
    assert elapsed
    assert len({match.start(1) - match.start() for match in elapsed}) == 1
    assert "Evaluating first · Bravo" not in rendered
    heading = "EXCLUDARR  Preview" if command == "preview" else "EXCLUDARR  Run results"
    assert "\n\n" + heading in rendered


@pytest.mark.parametrize(
    ("media_type", "shown", "hidden"),
    [
        ("movies", "Bravo", "Only on Sonarr"),
        ("series", "Only on Sonarr", "Bravo"),
    ],
)
def test_run_and_preview_filter_media_type(env, monkeypatch, media_type, shown, hidden):
    series = replace(MOVIES[0], key="sonarr:series:1", kind="series", title="Only on Sonarr")
    monkeypatch.setattr("excludarr.engine.build_sonarr_items", lambda client, level: [series])
    rule = {"action": "delete", "preview": False, "when": {"monitored": True}}
    env["write"](
        [
            {**rule, "name": "movies", "target": "radarr"},
            {**rule, "name": "series", "target": "sonarr", "level": "series"},
        ],
        integrations={
            "radarr": {"url": "http://r:7878", "api_key": "k"},
            "sonarr": {"url": "http://s:8989", "api_key": "k"},
        },
    )
    for key in ("radarr:movie:1", series.key):
        env["repo"].queue_add("removed rule", key, key, 0, datetime.now(UTC))

    result = env["invoke"]("preview", "--type", media_type)
    assert result.exit_code == 0, result.output
    assert shown in result.output and hidden not in result.output
    assert env["repo"].history() == []

    result = env["invoke"]("run", "--type", media_type, "-y")
    assert result.exit_code == 0, result.output
    assert shown in result.output and hidden not in result.output
    assert {row.rule for row in env["repo"].history()} == {media_type}
    other_key = series.key if media_type == "movies" else "radarr:movie:1"
    assert set(env["repo"].queue_for("removed rule")) == {other_key}


def test_run_shows_each_title_once_with_its_result(env):
    result = env["invoke"]("run", "-y")
    assert result.exit_code == 0, result.output
    assert result.output.count("Bravo") == 1
    assert "done" in result.output
    assert "8.00 GB freed" in result.output


@pytest.mark.parametrize("command", ["preview", "run"])
def test_movie_table_contains_cached_provider_and_viewer_names(env, monkeypatch, command):
    from types import SimpleNamespace

    from excludarr.clients.justwatch import JustWatchClient
    from excludarr.clients.plex import PlexItem
    from excludarr.clients.seerr import SeerrRequest
    from excludarr.clients.tautulli import HistoryRow

    env["write"](profile={"providers": ["Netflix"]})
    monkeypatch.setattr("excludarr.engine.build_radarr_items", lambda client: [MOVIES[0]])
    env["repo"].cache_set("jw:match:MOVIE:1", "movie", timedelta(days=1))
    env["repo"].cache_set(
        "jw:offers:v2:movie",
        [[0, 0, [[8, "FLATRATE", None], [9, "FLATRATE", None]]]],
        timedelta(days=1),
    )
    env["repo"].cache_set(
        "jw:providers:en_US",
        [
            {"id": 8, "clear_name": "Netflix", "short_name": "nfx", "monetization_types": []},
            {"id": 9, "clear_name": "Amazon", "short_name": "amz", "monetization_types": []},
        ],
        timedelta(days=1),
    )
    clients = Clients(
        radarr=object(),
        justwatch=JustWatchClient("en_US"),
        plex=SimpleNamespace(
            items_by_guid=lambda: {("movie", "tmdb://1"): PlexItem("1", "1", "movie")}
        ),
        tautulli=SimpleNamespace(
            history=lambda: [
                HistoryRow(datetime.now(UTC), "alice123", "Alice", "1", None, None, None, True),
            ]
        ),
        seerr=SimpleNamespace(
            requests=lambda: [
                SeerrRequest(
                    1,
                    1,
                    "movie",
                    1,
                    None,
                    datetime.now(UTC),
                    frozenset({"bob", "bobby"}),
                    frozenset(),
                    requester_name="Bobby",
                )
            ]
        ),
    )
    monkeypatch.setattr(Clients, "from_config", classmethod(lambda cls, cfg: clients))
    result = env["invoke"](command, "--details", *(["-y"] if command == "run" else []))
    assert result.exit_code == 0, result.output
    assert "Netflix" in result.output and "Alice" in result.output
    assert "alice123" not in result.output
    assert "Amazon" not in result.output
    assert "Bobby" in result.output


def test_run_without_yes_aborts_on_no(env):
    r = env["invoke"]("run")  # CliRunner has no input: confirm gets EOF -> abort
    assert r.exit_code != 0 and env["executed"] == []
    r = env["invoke"]("run", "-y")
    assert r.exit_code == 0 and len(env["executed"]) == 3
    assert env["repo"].history()[0].rule == "r"


def test_rescue_forever_adds_exception(env):
    key = "radarr:movie:1"
    env["repo"].queue_add("r", key, "Bravo", 5 * GB, datetime.now(UTC) + timedelta(days=3))
    r = env["invoke"]("rescue", key, "--rule", "r", "--forever")
    assert r.exit_code == 0, r.output
    assert key not in env["repo"].queue_for("r")
    assert key in env["repo"].exceptions_for("r")
    assert env["invoke"]("rescue", key, "--rule", "r", "--once").exit_code == 1


def test_config_error_exit_code_1_without_traceback(env, tmp_path):
    (tmp_path / "c.yml").write_text("nonsense: true")
    r = env["invoke"]("preview")
    assert r.exit_code == 1 and "Traceback" not in r.output and "error" in r.output


def test_sort_by_size(env, monkeypatch):
    # Input order (Bravo, Alpha, Charlie) differs from size order and from date order.
    movies = [movie(1, "Bravo", 2, 3), movie(2, "Alpha", 1, 2), movie(3, "Charlie", 5, 1)]
    monkeypatch.setattr("excludarr.engine.build_radarr_items", lambda r: list(movies))

    def order(sort):
        out = env["invoke"]("preview", "--sort", sort).output
        return sorted(["Alpha", "Bravo", "Charlie"], key=out.index)

    assert order("size") == ["Charlie", "Bravo", "Alpha"]
    assert order("title") == ["Alpha", "Bravo", "Charlie"]
    assert order("date") == ["Charlie", "Alpha", "Bravo"]
    now = datetime.now(UTC)
    for m in movies:
        env["repo"].queue_add("r", m.key, m.title, m.size_bytes, now)
    out = env["invoke"]("queue", "--sort", "size").output
    assert out.index("Charlie") < out.index("Bravo") < out.index("Alpha")


def test_confirm_no_and_yes(env):
    r = env["invoke"]("run", input="n\n")
    assert "Execute 3 actions (0.00 GB estimated space freed)?" in r.output and "Alpha" in r.output
    assert "Not executed" in r.output
    assert env["executed"] == []
    r = env["invoke"]("run", input="y\n")
    assert r.exit_code == 0 and len(env["executed"]) == 3


def test_markup_in_title_does_not_crash(env, monkeypatch):
    monkeypatch.setattr(
        "excludarr.engine.build_radarr_items", lambda r: [movie(1, "Bad [/y] [bold]x", 1)]
    )
    r = env["invoke"]("run", "-y")
    assert r.exit_code == 0, r.output
    assert "Bad [/y]" in r.output
    env["repo"].queue_add("r", "k", "Q [/y]", 1, datetime.now(UTC))
    assert env["invoke"]("queue").exit_code == 0


def test_exit_code_2_on_failed_action(env, monkeypatch):
    monkeypatch.setattr(
        "excludarr.engine.execute", lambda rule, item, ctx: ActionResult(False, 0, "boom")
    )
    result = env["invoke"]("run", "-y")
    assert result.exit_code == 2
    assert result.output.index("3 failed") < result.output.index("Bravo")
    assert "Failed" in result.output and "boom" in result.output


def test_rescue_once_adds_no_exception(env):
    key = "radarr:movie:1"
    env["repo"].queue_add("r", key, "Bravo", 1, datetime.now(UTC))
    assert env["invoke"]("rescue", key, "--rule", "r", "--once").exit_code == 0
    assert key not in env["repo"].queue_for("r") and env["repo"].exceptions_for("r") == set()


def test_rescue_prompt_is_strict(env):
    key = "radarr:movie:1"
    env["repo"].queue_add("r", key, "Bravo", 1, datetime.now(UTC))
    r = env["invoke"]("rescue", key, "--rule", "r", input="maybe\nforever\n")
    assert r.exit_code == 0 and key in env["repo"].exceptions_for("r")


def test_config_validate_checks_unless_providers(env, monkeypatch):
    from types import SimpleNamespace

    from excludarr.clients.justwatch import Provider

    monkeypatch.setattr(
        Clients,
        "from_config",
        classmethod(lambda cls, c: cls(radarr=object(), justwatch=SimpleNamespace(locale="en_US"))),
    )
    monkeypatch.setattr(
        "excludarr.facts.Context._providers",
        lambda self: [
            Provider(id=8, clear_name="Netflix", short_name="nfx", monetization_types=[])
        ],
    )
    rule = {"name": "r", "target": "radarr", "action": "delete", "when": {"monitored": True}}
    ok = {"streaming": {"providers": ["Netflix"]}}
    env["write"]([{**rule, "unless": [ok]}])
    r = env["invoke"]("config", "validate")
    assert r.exit_code == 0 and "OK" in r.output
    bad = {"streaming": {"providers": ["Nope"]}}
    env["write"]([{**rule, "unless": [bad]}])
    r = env["invoke"]("config", "validate")
    assert r.exit_code == 1 and "unknown provider" in r.output


def test_interactive_skips_numbers(env, monkeypatch):
    r = CliRunner().invoke(
        cli.app,
        ["--config", str(env["path"]), "run", "--interactive", "-y", "--sort", "title"],
        input="1\n",
    )
    assert r.exit_code == 0, r.output
    assert sorted(env["executed"]) == ["radarr:movie:1", "radarr:movie:3"]  # Alpha (#1) skipped


def test_interactive_invalid_input_reprompts(env):
    def go(inp):
        env["executed"].clear()
        args = ["run", "--interactive", "-y", "--sort", "title"]
        return env["invoke"](*args, input=inp)

    for bad in ("abc", "1-3", "9", "0", "\u0661"):
        r = go(f"{bad}\n2\n")
        assert "Enter numbers between 1 and 3" in r.output, bad
        assert sorted(env["executed"]) == ["radarr:movie:2", "radarr:movie:3"]  # Bravo (#2) skipped
    r = go("abc\n")  # EOF after invalid input: abort, nothing executed
    assert r.exit_code != 0 and env["executed"] == []


@pytest.mark.parametrize(
    "args",
    [
        ("run", "--rule", "X", "-y"),
        ("preview", "--rule", "X"),
        ("rescue", "radarr:movie:1", "--rule", "X", "--once"),
        ("exceptions", "remove", "radarr:movie:1", "--rule", "X"),
    ],
)
def test_unknown_rule_name_exits_1(env, args):
    r = env["invoke"](*args)
    assert r.exit_code == 1 and "unknown rule 'X'" in r.output
    assert env["executed"] == []


def test_orphan_rows_of_removed_rules_stay_manageable(env):
    env["repo"].exception_add("gone", "radarr:movie:1", "Bravo")
    r = env["invoke"]("exceptions", "remove", "radarr:movie:1", "--rule", "gone")
    assert r.exit_code == 0 and env["repo"].exceptions_for("gone") == set()
    env["repo"].queue_add("gone", "radarr:movie:1", "Bravo", 1, datetime.now(UTC))
    r = env["invoke"]("rescue", "radarr:movie:1", "--rule", "gone", "--once")
    assert r.exit_code == 0 and env["repo"].queue_all() == []


def test_debug_silences_httpx_request_logging(env):
    import logging

    env["invoke"]("--debug", "queue")
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING


@pytest.mark.parametrize("format,parse", [("json", json.loads), ("yaml", yaml.safe_load)])
def test_structured_output_and_confirmed_decline(env, format, parse):
    preview = env["invoke"]("preview", "-o", format)
    expanded = env["invoke"]("preview", "-o", format, "--details")
    assert preview.exit_code == expanded.exit_code == 0
    doc = parse(preview.stdout)
    assert doc == parse(expanded.stdout)
    assert doc["rules"][0]["matches"][0]["evidence"][0]["condition"] == "monitored"
    result = env["invoke"]("run", "-o", format, input="n\n")
    assert result.exit_code == 0
    assert "Execute" in result.stderr and "Execute" not in result.stdout
    assert "0.00 GB estimated space freed" in result.stderr
    assert parse(result.stdout)["status"] == "declined"
    assert env["executed"] == []


def test_structured_queue_reports_changed_rule_and_original_evidence(env):
    env["write"](
        [
            {
                "name": "r",
                "target": "radarr",
                "preview": False,
                "action": "unmonitor",
                "when": {"monitored": True},
            }
        ]
    )
    proof = [{"condition": "streaming", "result": True, "observed": {}}]
    env["repo"].queue_add(
        "r", "radarr:movie:1", "Film", 100, datetime.now(UTC) + timedelta(days=1), evidence=proof
    )
    result = env["invoke"]("queue", "-o", "json")
    assert result.exit_code == 0
    item = json.loads(result.stdout)["items"][0]
    assert item["planned_action"] == "Disable monitoring" and item["evidence"] == proof


def test_cache_status_reports_fetch_and_expiry_from_local_db(env, monkeypatch):
    def fail(cfg):
        pytest.fail("cache status constructed integration clients")

    monkeypatch.setattr(Clients, "from_config", fail)
    env["repo"].cache_set("jw:offers:v2:expired", [], timedelta(hours=-1))
    env["repo"].cache_set("jw:offers:v2:valid", [], timedelta(hours=1))
    report = env["invoke"]("--debug", "cache", "status", "-o", "json")
    assert report.exit_code == 0, report.output
    doc = json.loads(report.stdout)
    offers = next(group for group in doc["items"] if group["type"] == "Offers")
    assert offers["entries"] == 2 and offers["due"] == 1
    assert offers["oldest_fetched_at"] and offers["next_expiry_at"]
    assert doc["diagnostics"]["entries"][0]["key"] == "jw:offers:v2:expired"


def test_failed_forced_refresh_cannot_match_but_independent_any_can(env, monkeypatch):
    from types import SimpleNamespace

    from excludarr.clients.http import IntegrationError

    def fail():
        calls.append("providers")
        raise IntegrationError("justwatch", "offline")

    calls = []
    jw = SimpleNamespace(locale="en_US", providers=fail)
    monkeypatch.setattr(
        Clients, "from_config", classmethod(lambda cls, c: cls(radarr=object(), justwatch=jw))
    )
    env["write"](
        [
            {
                "name": name,
                "target": "radarr",
                "action": "unmonitor",
                "preview": False,
                "when": when,
            }
            for name, when in (
                ("streaming only", {"streaming": "my_providers"}),
                ("independent", {"any": [{"streaming": "my_providers"}, {"monitored": True}]}),
            )
        ],
        profile={"providers": ["Netflix"]},
    )
    env["repo"].cache_set(
        "jw:providers:en_US",
        [{"id": 8, "clear_name": "Netflix", "short_name": "nfx", "monetization_types": []}],
        timedelta(days=1),
    )
    for item in MOVIES:
        env["repo"].cache_set(f"jw:match:MOVIE:{item.tmdb_id}", "tm1", timedelta(days=1))
    env["repo"].cache_set("jw:offers:v2:tm1", [[0, 0, [[8, "FLATRATE", None]]]], timedelta(days=1))
    jw.search = lambda *args, **kwargs: (_ for _ in ()).throw(
        IntegrationError("justwatch", "offline")
    )
    result = env["invoke"]("run", "--refresh", "-y", "-o", "json")
    assert result.exit_code == 0, result.output
    guarded, independent = json.loads(result.stdout)["rules"]
    assert guarded["matches"] == []
    assert len(independent["matches"]) == len(MOVIES)
    assert independent["matches"][0]["evidence"][0]["condition"] == "monitored"
    assert calls == ["providers"]
    assert len(env["executed"]) == len(MOVIES)


@pytest.mark.parametrize("format,parse", [("json", json.loads), ("yaml", yaml.safe_load)])
def test_structured_run_reports_completed_actions_on_abort(env, format, parse):
    env["write"](
        [
            {
                "name": name,
                "target": "radarr",
                "action": "unmonitor",
                "preview": False,
                "when": {"monitored": True},
            }
            for name in ("first", "second")
        ]
    )
    result = env["invoke"]("run", "-o", format, input="y\n")
    assert result.exit_code == 1
    report = parse(result.stdout)
    assert report["status"] == "aborted"
    assert report["rules"][0]["matches"][0]["outcome"]["status"] == "done"
    assert report["rules"][1]["matches"][0]["outcome"]["status"] == "not_executed"


@pytest.mark.parametrize("format,parse", [("json", json.loads), ("yaml", yaml.safe_load)])
def test_structured_rescue_prompt_keeps_stdout_parseable(env, format, parse):
    env["repo"].queue_add("r", "radarr:movie:1", "Film", 100, datetime.now(UTC))
    result = env["invoke"]("rescue", "radarr:movie:1", "--rule", "r", "-o", format, input="\n")
    assert result.exit_code == 0
    assert parse(result.stdout)["items"][0]["forever"] is False
    assert "Rescue" in result.stderr


def test_structured_progress_keeps_report_stream_clean(env, monkeypatch):
    from types import SimpleNamespace

    import httpx
    import respx

    from excludarr.clients.http import HttpClient

    monkeypatch.setattr(cli, "Console", lambda **kwargs: Console(force_terminal=True, **kwargs))
    update = cli.Progress.update

    def render_wait(progress, *args, **kwargs):
        if kwargs.get("waiting"):
            kwargs["refresh"] = True
        return update(progress, *args, **kwargs)

    monkeypatch.setattr(cli.Progress, "update", render_wait)
    client = SimpleNamespace(http=HttpClient("radarr", "http://r", {}))
    monkeypatch.setattr(Clients, "from_config", classmethod(lambda cls, cfg: cls(radarr=client)))

    def load(radarr):
        radarr.http.get("/movie")
        return MOVIES

    monkeypatch.setattr("excludarr.engine.build_radarr_items", load)
    with respx.mock:
        respx.get("http://r/movie").mock(return_value=httpx.Response(200))
        result = env["invoke"]("preview", "--progress", "-o", "json")
    assert result.exit_code == 0
    assert "Waiting for Radarr" in result.stderr
    assert "3/3" in result.stderr
    assert json.loads(result.stdout)["summary"]["matches"] == 3


@pytest.mark.parametrize(
    "command",
    [
        ("queue",),
        ("history",),
        ("cache", "status"),
        ("exceptions", "list"),
        ("config", "validate"),
    ],
)
def test_structured_read_commands_emit_one_report(env, monkeypatch, command):
    from types import SimpleNamespace

    jw = SimpleNamespace(locale="en_US", providers=list)
    monkeypatch.setattr(Clients, "from_config", classmethod(lambda cls, c: cls(justwatch=jw)))
    result = env["invoke"](*command, "-o", "json")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["command"] == " ".join(command)


def test_structured_configuration_error_does_not_echo_yaml_source(env):
    env["path"].write_text("api_key: private_token: bad\n")
    result = env["invoke"]("config", "validate", "-o", "json")
    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert report["status"] == "error"
    assert "invalid YAML" in report["errors"][0]
    assert "private_token" not in result.output


@pytest.mark.parametrize("width", [120, 180])
def test_preview_keeps_every_match_in_narrow_tables(env, monkeypatch, width):
    library = [movie(i, f"Example movie {i:02d}", 1) for i in range(1, 11)]
    library[-1] = replace(
        library[-1], title="Example movie 10 with a long title that must wrap across multiple lines"
    )
    monkeypatch.setattr("excludarr.engine.build_radarr_items", lambda client: library)
    env["write"](
        [
            {
                "name": name,
                "target": "radarr",
                "action": "delete_files",
                "when": {"added_more_than": "180d"},
            }
            for name in ("First rule", "Second rule", "Third rule")
        ]
    )
    sink = StringIO()
    monkeypatch.setattr(
        cli, "Console", lambda **kwargs: Console(file=sink, width=width, height=18, **kwargs)
    )
    result = env["invoke"]("preview")
    assert result.exit_code == 0, result.output
    compact = Text.from_ansi(sink.getvalue()).plain
    assert compact.count("Example movie") == 30
    assert compact.count("multiple") == 3
    assert max(map(len, compact.splitlines())) == width
    assert "Next step" in compact and "Match evidence" in compact
    assert all(compact.count(name) == 11 for name in ("First rule", "Second rule", "Third rule"))
    assert compact.count("Clean up related download queue entries") == 1
    assert "10 unique titles" in compact and "After grace" not in compact
    assert "2020-01-01T" not in compact
    sink.seek(0)
    sink.truncate()
    assert env["invoke"]("preview", "--details").exit_code == 0
    expanded = Text.from_ansi(sink.getvalue()).plain
    assert expanded.count("Example movie") == 30
    assert "2020-01-01T" in expanded
    structured = env["invoke"]("preview", "-o", "json")
    assert structured.exit_code == 0, structured.output
    report = json.loads(structured.stdout)
    assert sum(len(rule["matches"]) for rule in report["rules"]) == 30
    assert env["executed"] == []


@pytest.mark.parametrize("command", ["run", "preview"])
@pytest.mark.parametrize("colored", [False, True])
def test_details_help_and_legacy_alias(env, monkeypatch, command, colored):
    monkeypatch.delenv("NO_COLOR", raising=False)
    if colored:
        monkeypatch.setenv("FORCE_COLOR", "1")
    else:
        monkeypatch.delenv("FORCE_COLOR", raising=False)
    help_result = env["invoke"](command, "--help")
    help_text = Text.from_ansi(help_result.output).plain
    assert "--details" in help_text
    assert "--show-all" not in help_text
    args = ["-y"] if command == "run" else []
    assert env["invoke"](command, "--show-all", *args).exit_code == 0


def test_rule_colors_are_distinct_in_overview_and_details(env, monkeypatch):
    import re

    sink = StringIO()
    monkeypatch.setattr(
        cli,
        "Console",
        lambda: Console(
            file=sink, force_terminal=True, color_system="truecolor", no_color=False, width=160
        ),
    )
    names = [f"color-rule-{index:02}" for index in range(20)]
    env["write"](
        [
            {"name": name, "target": "radarr", "action": "delete", "when": {"monitored": True}}
            for name in names
        ]
    )
    result = env["invoke"]("preview", "--details")
    assert result.exit_code == 0, result.output
    colors = []
    for name in names:
        styles = re.findall(r"\x1b\[([0-9;]+)m" + name, sink.getvalue())
        assert len(styles) >= 2  # Overview and matching titles share the rule color.
        rgb_styles = [style.removeprefix("1;") for style in styles]
        assert len(set(rgb_styles)) == 1
        colors.append(rgb_styles[0])
    assert len(set(colors)) == len(names)


@pytest.mark.parametrize("format", ["table", "json", "yaml"])
def test_quality_evidence_in_table_and_structured_preview(env, monkeypatch, format):
    from excludarr.facts import Context

    env["write"](
        [
            {
                "name": "quality",
                "target": "radarr",
                "action": "delete_files",
                "when": {"streaming": {"providers": ["Netflix"], "min_quality": "hd"}},
            }
        ]
    )
    monkeypatch.setattr(
        Context, "streaming", lambda self, item: [frozenset({(8, "FLATRATE", "4k")})]
    )
    monkeypatch.setattr(Context, "provider_ids", lambda *args: {8})
    monkeypatch.setattr(Context, "provider_names", lambda *args: {8: "Netflix"})
    result = env["invoke"]("preview", "-o", format)
    assert result.exit_code == 0, result.output
    if format == "table":
        text = Text.from_ansi(result.stdout).plain
        assert "min HD" in text and "4K" in text
    else:
        doc = json.loads(result.stdout) if format == "json" else yaml.safe_load(result.stdout)
        observed = doc["rules"][0]["matches"][0]["evidence"][0]["observed"]
        assert observed["min_quality"] == "hd"
        assert observed["matched_offers"] == [
            {"provider_id": 8, "type": "FLATRATE", "quality": "4k", "provider": "Netflix"}
        ]
    assert env["executed"] == []


def _arr_clients(monkeypatch, *, movies=None, series=None, sonarr_error=None):
    from types import SimpleNamespace

    from excludarr.clients.http import IntegrationError

    def sonarr_series():
        if sonarr_error:
            raise IntegrationError("sonarr", "down")
        return series or []

    clients = Clients(
        radarr=SimpleNamespace(movies=lambda: movies or []),
        sonarr=SimpleNamespace(series=sonarr_series),
    )
    monkeypatch.setattr(Clients, "from_config", classmethod(lambda cls, c: clients))


def test_rating_keys_prune_removes_ids_not_in_arr(env, monkeypatch):
    _arr_clients(monkeypatch, movies=[{"tmdbId": 1, "imdbId": "tt1"}], series=[{"tvdbId": 9}])
    env["repo"].rating_keys_record(
        {("movie", "tmdb://1"): "a", ("movie", "tmdb://2"): "b", ("show", "tvdb://9"): "c"}
    )
    result = env["invoke"]("rating-keys", "prune", "-o", "json")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["summary"] == {"removed": 1}
    assert env["repo"].rating_keys_for("movie", ["tmdb://1", "tmdb://2"]) == {"a"}
    assert env["repo"].rating_keys_for("show", ["tvdb://9"]) == {"c"}


def test_rating_keys_prune_keeps_unmonitored_items(env, monkeypatch):
    _arr_clients(monkeypatch, movies=[{"tmdbId": 1, "monitored": False}])
    env["repo"].rating_keys_record({("movie", "tmdb://1"): "a"})
    result = env["invoke"]("rating-keys", "prune")
    assert result.exit_code == 0, result.output
    assert "Removed 0 known rating keys" in result.output
    assert env["repo"].rating_keys_for("movie", ["tmdb://1"]) == {"a"}


def test_rating_keys_prune_deletes_nothing_on_integration_error(env, monkeypatch):
    _arr_clients(monkeypatch, sonarr_error=True)
    env["repo"].rating_keys_record({("movie", "tmdb://2"): "b", ("show", "tvdb://9"): "c"})
    result = env["invoke"]("rating-keys", "prune")
    assert result.exit_code == 1
    assert env["repo"].rating_keys_for("movie", ["tmdb://2"]) == {"b"}
    assert env["repo"].rating_keys_for("show", ["tvdb://9"]) == {"c"}


def test_rating_keys_prune_json(env, monkeypatch):
    _arr_clients(monkeypatch)
    result = env["invoke"]("rating-keys", "prune", "-o", "json")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["summary"]["removed"] == 0
