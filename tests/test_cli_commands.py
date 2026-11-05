from datetime import UTC, datetime, timedelta

import pytest
import yaml
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


def test_preview_prints_condition_counts_and_totals(env):
    r = env["invoke"]("preview")
    assert r.exit_code == 0, r.output
    assert "PREVIEW" in r.output or "AUTO" in r.output
    assert "condition" in r.output and "unknown" in r.output
    assert "Total: 3 matches, 8.00 GB" in r.output
    assert env["executed"] == []


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
    assert "Execute 3 actions (8.00 GB)?" in r.output and "Alpha" in r.output
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
    assert env["invoke"]("run", "-y").exit_code == 2


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
