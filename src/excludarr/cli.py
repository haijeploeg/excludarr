import logging
import sys
from contextlib import contextmanager, nullcontext, redirect_stdout
from dataclasses import asdict
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from threading import current_thread
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Column
from rich.text import Text

from excludarr import __version__, output, reporting
from excludarr.preview import action_description, reclaimable_files
from excludarr.reporting import OutputFormat

app = typer.Typer(help="Excludarr: rule engine for Radarr/Sonarr libraries.", no_args_is_help=True)

state: dict = {"config": None, "debug": False}
FormatOpt = Annotated[
    OutputFormat, typer.Option("-o", "--output", help="Table, JSON or YAML output.")
]
ShowAllOpt = Annotated[bool, typer.Option("--show-all", help="Show all available match context.")]
RefreshOpt = Annotated[bool, typer.Option("--refresh", help="Refresh cache entries as needed.")]


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
    format: FormatOpt = OutputFormat.table,
) -> None:
    """List JustWatch providers for a locale."""
    from excludarr.clients.justwatch import JustWatchClient
    from excludarr.config import ConfigError, find_config_path, load_config

    with _command("providers list", format) as doc:
        if locale is None:
            try:
                path = find_config_path(state["config"])
            except ConfigError:
                if state["config"]:
                    raise
                path = None
            locale = load_config(path)[0].profile.locale if path is not None else "en_US"
        client = JustWatchClient(locale)
        rows = [
            asdict(p) for p in sorted(client.providers(), key=lambda p: p.clear_name.casefold())
        ]
        doc["items"] = rows
        doc["summary"] = {"locale": client.locale, "count": len(rows)}
        if format == OutputFormat.table:
            output.print_rows(
                f"Providers · {client.locale}",
                {
                    "id": "ID",
                    "clear_name": "Name",
                    "short_name": "Short name",
                    "monetization_types": "Monetization types",
                },
                [
                    row | {"monetization_types": ", ".join(row["monetization_types"])}
                    for row in rows
                ],
                Console(),
            )


class Sort(StrEnum):
    title = "title"
    size = "size"
    date = "date"


class MediaType(StrEnum):
    movies = "movies"
    series = "series"


SortOpt = Annotated[Sort | None, typer.Option("--sort", help="Sort by title, size or date.")]
RuleOpt = Annotated[str | None, typer.Option("--rule", help="Only this rule.")]
MediaTypeOpt = Annotated[
    MediaType | None, typer.Option("--type", help="Only movies (Radarr) or series (Sonarr).")
]


@contextmanager
def _command(name: str, format: OutputFormat):
    """Own the final report and emit it once, including handled failures."""
    from excludarr.clients.http import IntegrationError
    from excludarr.config import ConfigError

    doc = reporting.document(name)

    def emit():
        if format != OutputFormat.table:
            typer.echo(reporting.serialize(doc, format))

    try:
        yield doc
    except (ConfigError, IntegrationError) as error:
        doc["status"] = "error"
        doc["errors"].append(str(error))
        typer.echo(f"error: {error}", err=True)
        emit()
        raise typer.Exit(1) from error
    except typer.Abort:
        doc["status"] = "aborted"
        emit()
        raise
    except typer.Exit:
        emit()
        raise
    else:
        emit()


def _prompt_output(format: OutputFormat):
    # Typer writes part of the input prompt to stdout even with err=True.
    return nullcontext() if format == OutputFormat.table else redirect_stdout(sys.stderr)


def _context(*, refresh: bool = False):
    from excludarr.config import database_url, load_config
    from excludarr.facts import Clients, Context
    from excludarr.storage.repo import Repo

    config, path = load_config(state["config"])
    repo = Repo(database_url(config, path))
    return Context(config, Clients.from_config(config), repo, datetime.now(UTC), refresh=refresh)


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


def _report(
    ctx,
    doc,
    *,
    dry_run,
    rule,
    sort,
    media_type,
    interactive=False,
    yes=True,
    show_progress=False,
    format=OutputFormat.table,
    show_all=False,
) -> None:
    from excludarr import engine
    from excludarr.clients.http import HttpClient

    _check_rule(ctx, rule)
    structured = format != OutputFormat.table
    show_context = structured or show_all
    console = Console(stderr=True) if structured else Console()
    progress = Progress(
        SpinnerColumn(style="cyan", finished_text="[green]✓[/green]"),
        TextColumn(
            "{task.description}",
            table_column=Column(width=max(12, min(48, console.width - 48)), no_wrap=True),
        ),
        TextColumn(
            "{task.fields[count]}",
            justify="right",
            table_column=Column(width=13, no_wrap=True),
        ),
        TimeElapsedColumn(table_column=Column(width=8, justify="right", no_wrap=True)),
        TextColumn("{task.fields[waiting]}", table_column=Column(no_wrap=True)),
        console=console,
        transient=False,
        redirect_stdout=not structured,
        redirect_stderr=not structured,
        disable=not (show_progress and console.is_terminal),
    )
    task = None
    phase = None

    def update_progress(message, done, total):
        nonlocal task, phase
        if progress.disable:
            return
        if message != phase:
            if task is not None:
                previous = progress.tasks[-1]
                progress.update(task, completed=previous.total or 1, total=previous.total or 1)
                progress.stop_task(task)
            task = progress.add_task(escape(message), total=total, count="", waiting="")
            phase = message
        progress.update(
            task,
            completed=done,
            count=f"{done}/{total}" if total is not None else "",
            refresh=done == total or done == 0,
        )
        if total is not None and done == total:
            progress.stop_task(task)
        progress.start()

    main_thread = current_thread()

    def integration_wait(name: str, active: bool) -> None:
        if task is not None and current_thread() is main_thread:
            label = escape(f"Waiting for {name.capitalize()}") if active else ""
            progress.update(task, waiting=label)

    clients = []
    if not progress.disable:
        clients = [
            client.http
            for client in vars(ctx.clients).values()
            if isinstance(getattr(client, "http", None), HttpClient)
        ]
        for client in clients:
            client.on_wait = integration_wait

    target = {MediaType.movies: "radarr", MediaType.series: "sonarr"}.get(media_type)
    details = {}
    reports = []

    def describe_matches(matches):
        if not show_context:
            return
        for done, match in enumerate(matches):
            update_progress("Loading item details", done, len(matches))
            item = match.item
            if item.key not in details:
                context = {
                    "tags": sorted(item.tags),
                    "monitored": item.monitored,
                    "has_file": item.has_file,
                }
                if item.added and item.kind in ("movie", "series"):
                    context["library_added_at"] = item.added.isoformat()
                if item.file_added_at:
                    date = item.file_added_at
                    if date.tzinfo is None:
                        date = date.replace(tzinfo=UTC)
                    context["file_added_at"] = date.isoformat()
                    context["file_age_seconds"] = max(0, (ctx.now - date).total_seconds())
                if ctx.clients.justwatch and ctx.config.profile.providers:
                    context["providers"] = ctx.streaming_labels(item)
                if item.kind == "movie" and ctx.clients.plex and ctx.clients.tautulli:
                    context["watched_by"] = ctx.movie_viewer_labels(item)
                if ctx.clients.seerr:
                    requests = ctx.requests(item)
                    context["requested_by"] = ctx.requester_labels(item)
                    context["requests"] = (
                        None
                        if requests is None
                        else [
                            {
                                "id": request.id,
                                "requester": request.requester_name,
                                "status": request.status,
                                "requested_at": request.created_at.isoformat(),
                                "seasons": sorted(request.seasons),
                            }
                            for request in requests
                        ]
                    )
                details[item.key] = context
            match.context = details[item.key]
        if matches:
            update_progress("Loading item details", len(matches), len(matches))

    def select(report):
        matches = reporting.sort_matches(report.matches, sort)
        if not matches:
            return matches
        progress.live.transient = True
        progress.stop()
        progress.live.transient = False
        console.print(f"\n{report.rule.name}", markup=False, style="bold")
        console.print(
            output.match_details(
                [reporting.match_row(m) for m in matches],
                numbered=True,
                show_all=show_all,
            )
        )
        with _prompt_output(format):
            while (
                skip := _parse_skip(
                    typer.prompt(
                        "Numbers to skip (comma separated, empty = none)",
                        default="",
                        err=structured,
                    ),
                    len(matches),
                )
            ) is None:
                typer.echo(f"Enter numbers between 1 and {len(matches)}, e.g. 1,3", err=structured)
        return [m for n, m in enumerate(matches, 1) if n not in skip]

    def confirm(matches):
        if yes:
            return True
        progress.live.transient = True
        progress.stop()
        progress.live.transient = False
        console.print(f"\n{action_description(matches[0].rule)}", markup=False, style="bold")
        if reports[-1].side_effects:
            console.print("On execution  " + "; ".join(reports[-1].side_effects), markup=False)
        console.print(
            output.match_details(
                [reporting.match_row(m) for m in reporting.sort_matches(matches, sort)],
                show_all=show_all,
            )
        )
        files = {}
        for match in matches:
            files.update(reclaimable_files(match))
        size = output.gb(sum(files.values()))
        with _prompt_output(format):
            return typer.confirm(
                f"Execute {len(matches)} actions ({size} estimated space freed)?",
                default=False,
                err=structured,
            )

    try:
        with progress:
            engine.run(
                ctx,
                dry_run=dry_run,
                diagnostics=state["debug"],
                on_report=reports.append,
                rule_filter=rule,
                target_filter=target,
                select=select if interactive else None,
                confirm=confirm,
                progress=update_progress,
                describe_matches=describe_matches,
            )
            if task is not None:
                last = progress.tasks[-1]
                progress.update(task, completed=last.total or 1, total=last.total or 1)
                progress.stop_task(task)
    finally:
        for client in clients:
            client.on_wait = None
        doc.update(
            reporting.run_document(reports, dry_run=dry_run, sort=sort, diagnostics=state["debug"])
        )
    if not structured:
        if task is not None and not progress.disable:
            console.print()
        output.print_reports(doc, console, show_all=show_all)
    if doc["summary"]["failed"]:
        raise typer.Exit(2)


@app.command()
def run(
    rule: RuleOpt = None,
    interactive: Annotated[bool, typer.Option("--interactive", help="Pick items to skip.")] = False,
    yes: Annotated[bool, typer.Option("-y", "--yes", help="Do not ask for confirmation.")] = False,
    sort: SortOpt = None,
    media_type: MediaTypeOpt = None,
    progress: Annotated[bool, typer.Option("--progress", help="Show live progress.")] = False,
    format: FormatOpt = OutputFormat.table,
    show_all: ShowAllOpt = False,
    refresh: RefreshOpt = False,
) -> None:
    """Evaluate the rules and execute actions (preview rules only report)."""
    with _command("run", format) as doc:
        _report(
            _context(refresh=refresh),
            doc,
            dry_run=False,
            rule=rule,
            sort=sort,
            media_type=media_type,
            interactive=interactive,
            yes=yes,
            show_progress=progress,
            format=format,
            show_all=show_all,
        )


@app.command()
def preview(
    rule: RuleOpt = None,
    sort: SortOpt = None,
    media_type: MediaTypeOpt = None,
    progress: Annotated[bool, typer.Option("--progress", help="Show live progress.")] = False,
    format: FormatOpt = OutputFormat.table,
    show_all: ShowAllOpt = False,
    refresh: RefreshOpt = False,
) -> None:
    """Report what the rules would do, without changing anything."""
    with _command("preview", format) as doc:
        _report(
            _context(refresh=refresh),
            doc,
            dry_run=True,
            rule=rule,
            sort=sort,
            media_type=media_type,
            show_progress=progress,
            format=format,
            show_all=show_all,
        )


cache_app = typer.Typer(help="Inspect the local cache.", no_args_is_help=True)
app.add_typer(cache_app, name="cache")


@cache_app.command("status")
def cache_status(format: FormatOpt = OutputFormat.table) -> None:
    """Show when local cache entries were fetched and are due for refresh."""
    from excludarr.config import database_url, load_config
    from excludarr.storage.repo import Repo

    with _command("cache status", format) as doc:
        config, path = load_config(state["config"])
        entries = Repo(database_url(config, path)).cache_metadata()
        doc.update(reporting.cache_status(entries, datetime.now(UTC), diagnostics=state["debug"]))
        if format == OutputFormat.table:
            output.print_cache(doc, Console())


@app.command()
def queue(sort: SortOpt = None, format: FormatOpt = OutputFormat.table) -> None:
    """List the grace queue."""
    with _command("queue", format) as doc:
        ctx = _context()
        rows = ctx.repo.queue_all()
        key = {"title": lambda q: q.title.casefold(), "size": lambda q: -q.size_bytes}
        if sort in key:
            rows = sorted(rows, key=key[sort])
        doc["items"] = reporting.queue_rows(rows, {rule.name: rule for rule in ctx.config.rules})
        doc["summary"] = {"count": len(rows)}
        if format == OutputFormat.table:
            output.print_queue(doc["items"], Console())


@app.command()
def rescue(
    item_key: str,
    rule: Annotated[str, typer.Option("--rule", help="Rule the item is queued for.")],
    forever: Annotated[bool, typer.Option("--forever", help="Also add an exception.")] = False,
    once: Annotated[bool, typer.Option("--once", help="Only leave the queue this time.")] = False,
    format: FormatOpt = OutputFormat.table,
) -> None:
    """Take an item out of the grace queue (and the Leaving Soon collection)."""
    from excludarr import engine
    from excludarr.config import ConfigError
    from excludarr.items import build_radarr_items, build_sonarr_items

    with _command("rescue", format) as doc:
        if forever and once:
            raise ConfigError("choose --forever or --once, not both")
        if not forever and not once:
            choice = ""
            with _prompt_output(format):
                while choice not in ("once", "forever"):
                    choice = typer.prompt(
                        "Rescue (once/forever)",
                        default="once",
                        err=format != OutputFormat.table,
                    ).strip()
            forever = choice == "forever"
        ctx = _context()
        row = ctx.repo.queue_for(rule).get(item_key)
        if row is None:
            _check_rule(ctx, rule)
            raise ConfigError(f"{item_key} is not queued for rule {rule!r}")
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
            except Exception as error:  # noqa: BLE001 - collection cleanup never blocks rescue
                doc["warnings"] = [f"Leaving Soon collection not updated: {error}"]
                typer.echo(f"warning: {doc['warnings'][0]}", err=True)
        doc["items"] = [
            {"item_key": item_key, "rule": rule, "title": row.title, "forever": forever}
        ]
        if format == OutputFormat.table:
            output.heading(Console(), f"Rescued {row.title} ({'forever' if forever else 'once'})")


exceptions_app = typer.Typer(help="Persistent exceptions.", no_args_is_help=True)
app.add_typer(exceptions_app, name="exceptions")


@exceptions_app.command("list")
def exceptions_list(format: FormatOpt = OutputFormat.table) -> None:
    """List exceptions."""
    with _command("exceptions list", format) as doc:
        rows = [
            asdict(row) | {"created_at": row.created_at.isoformat()}
            for row in _context().repo.exceptions_all()
        ]
        doc["items"] = rows
        doc["summary"] = {"count": len(rows)}
        if format == OutputFormat.table:
            output.print_rows(
                "Exceptions",
                {
                    "rule": "Rule",
                    "item_key": "Key",
                    "title": "Title",
                    "created_at": "Added (UTC)",
                },
                rows,
                Console(),
            )


@exceptions_app.command("remove")
def exceptions_remove(
    item_key: str,
    rule: Annotated[str, typer.Option("--rule", help="Rule name.")],
    format: FormatOpt = OutputFormat.table,
) -> None:
    """Remove an exception."""
    with _command("exceptions remove", format) as doc:
        ctx = _context()
        if item_key not in ctx.repo.exceptions_for(rule):
            _check_rule(ctx, rule)
        ctx.repo.exception_remove(rule, item_key)
        doc["items"] = [{"item_key": item_key, "rule": rule}]
        if format == OutputFormat.table:
            output.heading(Console(), "Removed exception")


@app.command()
def history(
    limit: Annotated[int, typer.Option("--limit")] = 100, format: FormatOpt = OutputFormat.table
) -> None:
    """Show executed actions."""
    with _command("history", format) as doc:
        doc["items"] = reporting.history_rows(_context().repo.history(limit))
        doc["summary"] = {"count": len(doc["items"])}
        if format == OutputFormat.table:
            output.print_history(doc["items"], Console())


config_app = typer.Typer(help="Configuration.", no_args_is_help=True)
app.add_typer(config_app, name="config")


@config_app.command("validate")
def config_validate(format: FormatOpt = OutputFormat.table) -> None:
    """Load the config, resolve provider names and describe the rules."""
    from excludarr.conditions import describe
    from excludarr.engine import provider_lists

    with _command("config validate", format) as doc:
        ctx = _context()
        proxy_rules = ctx.config.list_proxy.lists if ctx.config.list_proxy else {}
        for providers in provider_lists([*ctx.config.rules, *proxy_rules.values()]):
            ctx.provider_ids(providers)
        ctx.provider_ids(ctx.config.profile.providers)
        doc["items"] = [
            {
                "rule": rule.name,
                "condition": describe(rule.when),
                "action": action_description(rule),
            }
            for rule in ctx.config.rules
        ]
        doc["items"].extend(
            {
                "rule": name,
                "condition": describe(rule.when),
                "action": f"Exclude from {rule.target.title()} import list",
            }
            for name, rule in proxy_rules.items()
        )
        doc["summary"] = {"valid": True, "count": len(doc["items"])}
        if format == OutputFormat.table:
            output.print_rows(
                "Config · OK",
                {
                    "rule": "Rule",
                    "condition": "Condition",
                    "action": "Action",
                },
                doc["items"],
                Console(),
            )


def main() -> None:
    app()


lists_app = typer.Typer(help="Filtered source lists.", no_args_is_help=True)
app.add_typer(lists_app, name="lists")


def _list_config():
    from excludarr.config import ConfigError, database_url, load_config
    from excludarr.storage.repo import Repo

    config, path = load_config(state["config"])
    if config.list_proxy is None:
        raise ConfigError("list_proxy is not configured")
    return config, Repo(database_url(config, path))


def _list_refresh(name: str | None, format: OutputFormat, *, publish: bool):
    from excludarr.clients.http import IntegrationError
    from excludarr.config import ConfigError
    from excludarr.lists.service import refresh_list

    with _command("lists refresh" if publish else "lists preview", format) as doc:
        config, repo = _list_config()
        names = [name] if name is not None else list(config.list_proxy.lists)
        if any(n not in config.list_proxy.lists for n in names):
            raise ConfigError("unknown outgoing list")
        failed = False
        for slug in names:
            try:
                result = refresh_list(config, slug, repo, datetime.now(UTC), publish=publish)
                doc["items"].append(result)
                failed |= any(
                    item.get("unknown", False) and item["decision"] == "excluded"
                    for item in result["items"]
                )
            except (IntegrationError, ConfigError) as error:
                doc["errors"].append(str(error))
                failed = True
        doc["summary"] = {"lists": len(names), "failed": len(doc["errors"])}
        if failed:
            doc["status"] = "error" if doc["errors"] else "incomplete"
        if format == OutputFormat.table:
            rows = [
                {
                    "list": result["name"],
                    "included": Text(str(result["summary"]["included"]), style="green"),
                    "excluded": Text(str(result["summary"]["excluded"]), style="yellow"),
                }
                for result in doc["items"]
            ]
            output.print_rows(
                "Lists",
                {"list": "List", "included": "Included", "excluded": "Excluded"},
                rows,
                Console(),
            )
            for result in doc["items"]:
                details = []
                for item in result["items"]:
                    reason = item.get("reason") or output.evidence_text(item["evidence"])
                    if item.get("unknown") and item["decision"] == "included":
                        reason = "Required data unavailable; allowed by on_unknown: include"
                    elif item.get("unknown"):
                        reason = "Required data unavailable; blocked by on_unknown: exclude"
                    details.append(
                        item
                        | {
                            "decision": Text(
                                item["decision"],
                                style="green" if item["decision"] == "included" else "yellow",
                            ),
                            "reason": reason,
                        }
                    )
                output.print_rows(
                    result["name"],
                    {"title": "Title", "decision": "Decision", "reason": "Match evidence"},
                    details,
                    Console(),
                )
            for error in doc["errors"]:
                typer.echo("error: " + error, err=True)
        if failed:
            raise typer.Exit(1)


@lists_app.command("refresh")
def lists_refresh(
    name: Annotated[str | None, typer.Argument()] = None, format: FormatOpt = OutputFormat.table
):
    """Refresh and publish one or all outgoing lists."""
    _list_refresh(name, format, publish=True)


@lists_app.command("preview")
def lists_preview(name: str, format: FormatOpt = OutputFormat.table):
    """Evaluate a list without publishing a snapshot."""
    _list_refresh(name, format, publish=False)


@lists_app.command("status")
def lists_status(format: FormatOpt = OutputFormat.table):
    """Show local snapshot freshness and last refresh outcome."""
    from excludarr.lists.service import fingerprint, snapshot_valid

    with _command("lists status", format) as doc:
        config, repo = _list_config()
        now = datetime.now(UTC)
        for name in config.list_proxy.lists:
            snapshot = repo.list_snapshot(name)
            doc["items"].append(
                {
                    "name": name,
                    "valid": snapshot_valid(snapshot, fingerprint(config, name), now),
                    "successful_at": snapshot.successful_at.isoformat()
                    if snapshot and snapshot.successful_at
                    else None,
                    "last_attempt_at": snapshot.last_attempt_at.isoformat() if snapshot else None,
                    "age_seconds": (now - snapshot.successful_at).total_seconds()
                    if snapshot and snapshot.successful_at
                    else None,
                    "last_error": snapshot.last_error if snapshot else None,
                    "included": None,
                    "excluded": None,
                    **(snapshot.report.get("summary", {}) if snapshot and snapshot.report else {}),
                }
            )
        if format == OutputFormat.table:
            output.print_rows(
                "List snapshots",
                {
                    "name": "List",
                    "valid": "Valid",
                    "successful_at": "Last success (UTC)",
                    "included": "Included",
                    "excluded": "Excluded",
                    "last_error": "Last error",
                },
                [
                    row
                    | {
                        key: "—" if row[key] is None else row[key]
                        for key in ("included", "excluded")
                    }
                    for row in doc["items"]
                ],
                Console(),
            )


@app.command("serve")
def serve(
    host: Annotated[str, typer.Option(help="Bind address.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65535, help="HTTP port.")] = 8989,
):
    """Serve authenticated list snapshots; run refresh separately."""
    from excludarr.config import ConfigError
    from excludarr.lists.server import make_server

    with _command("serve", OutputFormat.table):
        config, repo = _list_config()
        try:
            server = make_server(config, repo, host, port)
        except OSError as error:
            raise ConfigError("cannot bind list server address") from error
        typer.echo(f"Serving list snapshots on {host}:{port}", err=True)
        output.print_rows(
            "List endpoints",
            {"name": "List", "target": "Target", "url": "URL"},
            [
                {
                    "name": name,
                    "target": rule.target.title(),
                    "url": f"http://{host}:{port}/lists/{name}",
                }
                for name, rule in config.list_proxy.lists.items()
            ],
            Console(stderr=True),
        )
        typer.echo("Append ?apikey=<API_KEY> to each URL using your list_proxy.api_key.", err=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
