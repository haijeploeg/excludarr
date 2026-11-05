import logging
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from excludarr import __version__, output

app = typer.Typer(help="Excludarr: rule engine for Radarr/Sonarr libraries.", no_args_is_help=True)

state: dict = {"config": None, "debug": False}


def _version(value: bool) -> None:
    if value:
        typer.echo(f"excludarr {__version__}")
        raise typer.Exit()


@app.callback()
def callback(
    config: Annotated[
        Path | None,
        typer.Option("--config", envvar="EXCLUDARR_CONFIG", help="Path to the config file."),
    ] = None,
    debug: Annotated[bool, typer.Option("--debug", help="Enable debug logging.")] = False,
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version, is_eager=True, help="Show version and exit."),
    ] = False,
) -> None:
    state["config"] = config
    state["debug"] = debug
    logging.basicConfig(level=logging.DEBUG if debug else logging.WARNING)
    # httpx logs request URLs, and Tautulli's apikey is a query parameter.
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)


providers_app = typer.Typer(help="Streaming providers.", no_args_is_help=True)
app.add_typer(providers_app, name="providers")


@providers_app.command("list")
def providers_list(
    locale: Annotated[str | None, typer.Option("--locale", help="e.g. nl_NL")] = None,
) -> None:
    """List JustWatch providers for a locale."""
    from excludarr.clients.http import IntegrationError
    from excludarr.clients.justwatch import JustWatchClient
    from excludarr.config import ConfigError, find_config_path, load_config

    if locale is None:
        try:
            path = find_config_path(state["config"])
        except ConfigError as e:
            if state["config"]:
                typer.echo(f"error: {e}", err=True)
                raise typer.Exit(1) from e
            path = None  # no config file anywhere: fall back to the default locale
        if path is None:
            locale = "en_US"
        else:
            try:
                locale = load_config(path)[0].profile.locale
            except ConfigError as e:
                typer.echo(f"error: {e}", err=True)
                raise typer.Exit(1) from e
    try:
        providers = JustWatchClient(locale).providers()
    except IntegrationError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(1) from e
    table = Table("id", "name", "short name", "monetization types")
    for p in sorted(providers, key=lambda p: p.clear_name.lower()):
        table.add_row(str(p.id), p.clear_name, p.short_name, ", ".join(p.monetization_types))
    Console().print(table)


class Sort(StrEnum):
    title = "title"
    size = "size"
    date = "date"


SortOpt = Annotated[Sort | None, typer.Option("--sort", help="Sort by title, size or date.")]
RuleOpt = Annotated[str | None, typer.Option("--rule", help="Only this rule.")]


@contextmanager
def _errors():
    """Print expected errors without a traceback and exit 1."""
    from excludarr.clients.http import IntegrationError
    from excludarr.config import ConfigError

    try:
        yield
    except (ConfigError, IntegrationError) as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(1) from e


def _context():
    from excludarr.config import database_url, load_config
    from excludarr.facts import Clients, Context
    from excludarr.storage.repo import Repo

    config, path = load_config(state["config"])
    repo = Repo(database_url(config, path))
    return Context(config, Clients.from_config(config), repo, datetime.now(UTC))


def _check_rule(ctx, rule: str | None) -> None:
    from excludarr.config import ConfigError

    if rule is not None and rule not in {r.name for r in ctx.config.rules}:
        raise ConfigError(f"unknown rule {rule!r}")


def _parse_skip(raw: str, n: int) -> set[int] | None:
    """Strict parse of '1, 3': ASCII integers within 1..n; None when invalid."""
    tokens = [t.strip() for t in raw.split(",")] if raw.strip() else []
    if not all(t.isascii() and t.isdigit() and 1 <= int(t) <= n for t in tokens):
        return None
    return {int(t) for t in tokens}


def _report(ctx, *, dry_run, rule, sort, interactive=False, yes=True) -> None:
    from excludarr import engine

    _check_rule(ctx, rule)

    def select(report):
        matches = output.sort_matches(report.matches, sort)
        if not matches:
            return matches
        output.Console().print(f"\n{report.rule.name}")
        output.Console().print(output.matches_table(matches, numbered=True))
        while (
            skip := _parse_skip(
                typer.prompt("Numbers to skip (comma separated, empty = none)", default=""),
                len(matches),
            )
        ) is None:
            typer.echo(f"Enter numbers between 1 and {len(matches)}, e.g. 1,3")
        return [m for n, m in enumerate(matches, 1) if n not in skip]

    def confirm(matches):
        if yes:
            return True
        output.Console().print(output.matches_table(matches))
        size = output.gb(sum(m.item.size_bytes for m in matches))
        return typer.confirm(f"Execute {len(matches)} actions ({size})?", default=False)

    reports = engine.run(
        ctx,
        dry_run=dry_run,
        rule_filter=rule,
        select=select if interactive else None,
        confirm=confirm,
    )
    for r in reports:
        output.print_report(r, sort)
    if any(not res.ok for r in reports for _, res in r.executed):
        raise typer.Exit(2)


@app.command()
def run(
    rule: RuleOpt = None,
    interactive: Annotated[bool, typer.Option("--interactive", help="Pick items to skip.")] = False,
    yes: Annotated[bool, typer.Option("-y", "--yes", help="Do not ask for confirmation.")] = False,
    sort: SortOpt = None,
) -> None:
    """Evaluate the rules and execute actions (preview rules only report)."""
    with _errors():
        _report(_context(), dry_run=False, rule=rule, sort=sort, interactive=interactive, yes=yes)


@app.command()
def preview(rule: RuleOpt = None, sort: SortOpt = None) -> None:
    """Report what the rules would do, without changing anything."""
    with _errors():
        _report(_context(), dry_run=True, rule=rule, sort=sort)


@app.command()
def queue(sort: SortOpt = None) -> None:
    """List the grace queue."""
    with _errors():
        rows = _context().repo.queue_all()
    key = {"title": lambda q: q.title.lower(), "size": lambda q: -q.size_bytes}
    output.print_queue(sorted(rows, key=key[sort]) if sort in key else rows)


@app.command()
def rescue(
    item_key: str,
    rule: Annotated[str, typer.Option("--rule", help="Rule the item is queued for.")],
    forever: Annotated[bool, typer.Option("--forever", help="Also add an exception.")] = False,
    once: Annotated[bool, typer.Option("--once", help="Only leave the queue this time.")] = False,
) -> None:
    """Take an item out of the grace queue (and the Leaving Soon collection)."""
    from excludarr import engine
    from excludarr.items import build_radarr_items, build_sonarr_items

    if forever and once:
        typer.echo("error: choose --forever or --once, not both", err=True)
        raise typer.Exit(1)
    if not forever and not once:
        choice = ""
        while choice not in ("once", "forever"):
            choice = typer.prompt("Rescue (once/forever)", default="once").strip()
        forever = choice == "forever"
    with _errors():
        ctx = _context()
        row = ctx.repo.queue_for(rule).get(item_key)
        if row is None:
            _check_rule(ctx, rule)
            typer.echo(f"error: {item_key} is not queued for rule {rule!r}", err=True)
            raise typer.Exit(1)
        ctx.repo.queue_remove(rule, item_key)
        if forever:
            ctx.repo.exception_add(rule, item_key, row.title)
        if ctx.clients.plex:
            target, kind = item_key.split(":")[:2]
            try:
                items = (
                    build_radarr_items(ctx.clients.radarr)
                    if target == "radarr"
                    else build_sonarr_items(ctx.clients.sonarr, kind)
                )
                engine._uncollect(ctx, next((i for i in items if i.key == item_key), None))
            except Exception as e:  # noqa: BLE001 - the collection never blocks a rescue
                typer.echo(f"warning: Leaving Soon collection not updated: {e}", err=True)
    typer.echo(f"Rescued {row.title} ({'forever' if forever else 'once'})")


exceptions_app = typer.Typer(help="Persistent exceptions.", no_args_is_help=True)
app.add_typer(exceptions_app, name="exceptions")


@exceptions_app.command("list")
def exceptions_list() -> None:
    """List exceptions."""
    with _errors():
        output.print_exceptions(_context().repo.exceptions_all())


@exceptions_app.command("remove")
def exceptions_remove(
    item_key: str, rule: Annotated[str, typer.Option("--rule", help="Rule name.")]
) -> None:
    """Remove an exception."""
    with _errors():
        ctx = _context()
        if item_key not in ctx.repo.exceptions_for(rule):
            _check_rule(ctx, rule)
        ctx.repo.exception_remove(rule, item_key)
    typer.echo("Removed")


@app.command()
def history(limit: Annotated[int, typer.Option("--limit")] = 100) -> None:
    """Show executed actions."""
    with _errors():
        output.print_history(_context().repo.history(limit))


config_app = typer.Typer(help="Configuration.", no_args_is_help=True)
app.add_typer(config_app, name="config")


@config_app.command("validate")
def config_validate() -> None:
    """Load the config, resolve provider names and describe the rules."""
    from excludarr.conditions import describe
    from excludarr.engine import provider_lists

    with _errors():
        ctx = _context()
        for providers in provider_lists(ctx.config.rules):
            ctx.provider_ids(providers)
        ctx.provider_ids(ctx.config.profile.providers)
        typer.echo("OK")
        for rule in ctx.config.rules:
            typer.echo(f"{rule.name}: {describe(rule.when)}")


def main() -> None:
    app()
