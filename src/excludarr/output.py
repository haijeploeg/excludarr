"""Rich views of the command report records."""

from colorsys import hls_to_rgb
from datetime import datetime

from rich import box
from rich.console import Console
from rich.table import Column, Table
from rich.text import Text

from excludarr.conditions import UnknownReason


def gb(n: int) -> str:
    return f"{n / 1024**3:.2f} GB"


def report_table(*headers: str) -> Table:
    return Table(
        *(
            Column(
                header,
                overflow="fold",
                min_width=10 if header in ("At (UTC)", "Due (UTC)") else None,
                justify="right"
                if header in ("Size", "Matched size", "Freed", "Matches")
                else "left",
            )
            for header in headers
        ),
        box=box.SIMPLE_HEAD,
        border_style="bright_black",
        header_style="bold cyan",
    )


def heading(console: Console, title: str) -> None:
    console.print(Text.assemble(("EXCLUDARR", "bold cyan"), f"  {title}"))


def cells(table: Table, values) -> None:
    table.add_row(*(value if isinstance(value, Text) else Text(str(value)) for value in values))


def _at(value: str | None) -> str:
    return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M:%S") if value else "—"


def _duration(seconds: float) -> str:
    if seconds >= 86400:
        return f"{seconds / 86400:g} days"
    if seconds >= 3600:
        return f"{seconds / 3600:g} hours"
    return f"{seconds:g} seconds"


def evidence_text(entries: list[dict] | None, *, compact: bool = False) -> str:
    parts = []
    for entry in entries or ():
        values = entry["observed"]
        label = entry.get("label") or entry["condition"]
        if "matched_offers" in values:
            found = (
                ", ".join(
                    f"{offer.get('provider', offer['provider_id'])} · "
                    f"{'subscription' if offer['type'] == 'FLATRATE' else offer['type'].lower()}"
                    f" · {offer['quality'].upper() if offer.get('quality') else 'quality unknown'}"
                    for offer in values["matched_offers"]
                )
                or "no qualifying offers"
            )
            if values.get("min_quality"):
                found += f" · min {values['min_quality'].upper()}"
            if values["total_units"] > 1:
                found += f" ({values['covered_units']}/{values['total_units']} episodes)"
            label = found if entry["result"] else f"{label} ({found})"
        elif compact and entry["result"] and "age_seconds" in values:
            age = values["age_seconds"]
            age_text = (
                f"{age / 86400:.1f}d"
                if age is not None and age >= 86400
                else f"{age / 3600:.1f}h"
                if age is not None
                else None
            )
            condition = entry["condition"]
            threshold = values.get("threshold_seconds")
            if condition.startswith("added_"):
                comparison = ">" if condition == "added_more_than" else "<"
                limit = label.split(" than ")[-1].removesuffix(" ago")
                label = f"Added {age_text} ago ({comparison}{limit})"
            elif condition == "requester_watched_more_than" and threshold is not None:
                requester = values.get("requester") or "Requester"
                label = f"{requester} watched {age_text} ago (>{threshold / 86400:g}d)"
            elif condition in ("not_watched_for", "watched_within") and threshold is not None:
                comparison = ">" if condition == "not_watched_for" else "≤"
                label = (
                    f"Last play {age_text} ago ({comparison}{threshold / 86400:g}d)"
                    if age_text
                    else f"No play recorded ({threshold / 86400:g}d rule)"
                )
            else:
                observation = " · ".join(filter(None, (values.get("requester"), age_text)))
                label += f" ({observation or 'no play recorded'})"
        elif (
            compact
            and entry["result"]
            and entry["condition"] in ("monitored", "has_file", "status", "fully_watched")
        ):
            pass
        elif values:
            observed = []
            for name, value in values.items():
                if isinstance(value, list):
                    value = ", ".join(map(str, value)) or "none"
                elif name.endswith("_seconds") and value is not None:
                    value = f"{value / 86400:.1f}d" if value >= 86400 else f"{value / 3600:.1f}h"
                elif name == "size_bytes" and value is not None:
                    value = gb(value)
                observed.append(
                    f"{name.removesuffix('_seconds').replace('_', ' ')} {value if value is not None else 'none'}"
                )
            label += " (" + ", ".join(observed) + ")"
        parts.append(label if entry["result"] else f"{label}: false")
    return " · ".join(parts) or "—"


OUTCOMES = {
    "done": ("Done", "green"),
    "done_with_warning": ("Done with warning", "yellow"),
    "failed": ("Failed", "red"),
    "queued": ("Queued", "cyan"),
    "pending": ("Waiting", "yellow"),
    "skipped": ("Skipped", "dim"),
    "declined": ("Not executed · declined", "dim"),
    "not_executed": ("Not executed", "dim"),
}
STEPS = {
    "execute": ("Would execute", "green"),
    "queue": ("Would queue", "cyan"),
    "wait": ("Wait", "yellow"),
    "skip": ("Skip · earlier removal", "dim"),
    "preview": ("Preview only", "dim"),
}
CONTEXT_LABELS = {
    "providers": "Providers",
    "watched_by": "Watched by",
    "requested_by": "Requested by",
    "requests": "Request details",
    "tags": "Label",
    "file_added_at": "Latest file added (UTC)",
    "file_age_seconds": "File age",
    "library_added_at": "Library added (UTC)",
}


def _next_step(row: dict) -> Text:
    outcome = row.get("outcome")
    step = row.get("next_step")
    if outcome:
        label, style = OUTCOMES[outcome["status"]]
        result = Text(label, style=style)
        for detail in [outcome.get("detail"), *outcome.get("side_effect_errors", [])]:
            if detail:
                result.append(f" · {detail}")
    else:
        label, style = STEPS.get(step, ("Ready for confirmation", "green"))
        if step == "execute" and row["due_at"]:
            label = "Due now"
        result = Text(label, style=style)
    if row["due_at"] and (step in ("queue", "wait") or outcome and outcome["status"] == "pending"):
        result.append(f" · {_at(row['due_at'])} UTC")
    return result


def _extra_context(values: dict) -> str:
    lines = []
    for name, label in CONTEXT_LABELS.items():
        if name not in values:
            continue
        value = values[name]
        if name == "requests" and value:
            value = ", ".join(
                f"#{entry['id']} ({entry['status'] if entry['status'] is not None else 'status unavailable'})"
                for entry in value
            )
        elif isinstance(value, list):
            value = ", ".join(value) or "None"
        elif name.endswith("_at"):
            value = _at(value)
        elif name == "file_age_seconds" and value is not None:
            value = _duration(value)
        lines.append(f"{label}: {value if value is not None else 'Unavailable'}")
    return "\n".join(lines) or "—"


def match_details(
    rows: list[dict],
    *,
    numbered: bool = False,
    show_all: bool = False,
    preview: bool = False,
    rule_styles: dict[str, str] | None = None,
) -> Table:
    headers = ["Title", "Rule", "Size", "Match evidence", "Next step" if preview else "Result"]
    if numbered:
        headers.insert(0, "#")
    if show_all:
        headers.append("Context")
    table = report_table(*headers)
    table.show_edge = not (preview and not show_all)
    table.expand = True
    for index, row in enumerate(rows, 1):
        values = [
            row["title"],
            Text(row["rule"], style=(rule_styles or {}).get(row["rule"], "")),
            gb(row["size_bytes"]),
            evidence_text(row["evidence"], compact=preview and not show_all),
            _next_step(row),
        ]
        if numbered:
            values.insert(0, str(index))
        if show_all:
            values.append(_extra_context(row["context"]))
        cells(table, values)
    return table


def print_reports(doc: dict, console: Console, *, show_all: bool = False) -> None:
    rules = doc["rules"]
    if not rules:
        heading(console, "Preview" if doc["command"] == "preview" else "Run results")
        console.print("No enabled rules match this selection.")
        return
    dry_run = doc["command"] == "preview"
    summary = doc["summary"]
    title = "Preview · no changes" if dry_run else "Run results"
    media = {"movie": "Movies", "series": "Series", "season": "Seasons", "episode": "Episodes"}
    levels = {rule["media"] for rule in rules}
    if len(levels) == 1:
        title += f" · {media[next(iter(levels))]}"
    heading(console, title)
    if summary["failed"]:
        console.print(Text(f"{summary['failed']} failed", style="red"))
    if dry_run:
        console.print()
        console.print(
            "No actions will be executed. Use 'excludarr run' to apply changes.",
            style="yellow",
            highlight=False,
        )
        protected = [rule["name"] for rule in rules if rule["preview_only"]]
        if protected:
            hint = (
                "All rules are preview-only. Set preview: false on the rules you want to run."
                if len(protected) > 1 and len(protected) == len(rules)
                else "Before executing, set preview: false for: " + ", ".join(protected)
            )
            console.print(Text(hint, style="yellow"))
        console.print()
    rule_styles = {}
    for index, rule in enumerate(rules):
        # Golden-angle spacing keeps earlier colors stable when more rules are added.
        rgb = hls_to_rgb((0.5 + index * 0.61803398875) % 1, 0.45, 0.7)
        rule_styles[rule["name"]] = "#{:02x}{:02x}{:02x}".format(
            *(round(channel * 255) for channel in rgb)
        )
    show_timing = not dry_run or any(rule["grace_seconds"] for rule in rules)
    diagnostics = any("diagnostics" in rule for rule in rules)
    headers = ["Rule", "Action", "Matches", "Matched size"]
    if show_timing:
        headers.append("When")
    if len(levels) > 1:
        headers.insert(1, "Media")
    if diagnostics:
        headers.append("Unknown")
    table = report_table(*headers)
    table.show_edge = not (dry_run and not show_all)
    for rule in rules:
        timing = "Immediately"
        if rule["preview_only"] and not dry_run:
            timing = "Preview only"
        elif rule["grace_seconds"]:
            timing = f"Grace {_duration(rule['grace_seconds'])}"
        name = rule["name"]
        row = [
            Text(name, style=f"bold {rule_styles[name]}"),
            rule["action"],
            str(rule["match_count"]),
            gb(rule["matched_size_bytes"]) if rule["match_count"] else "—",
        ]
        if show_timing:
            row.append(timing)
        if len(levels) > 1:
            row.insert(1, media[rule["media"]])
        if diagnostics:
            row.append(str(rule["diagnostics"]["unknown_count"]))
        cells(table, row)
    console.print(table)
    if dry_run:
        console.print()
        savings = Text.assemble(
            (f"{summary['unique_titles']} unique titles", "bold"),
            " · Estimated space freed on execution ",
            (gb(summary["estimated_now_bytes"]), "green"),
        )
        if summary["estimated_after_grace_bytes"]:
            savings.append(" · After grace ")
            savings.append(gb(summary["estimated_after_grace_bytes"]), style="cyan")
        console.print(savings)
        if any(rule["grace_seconds"] and rule["match_count"] for rule in rules):
            console.print("Queued items are re-evaluated when due.", style="dim")
    elif summary["size_freed_bytes"] or summary["cleanup_warnings"]:
        console.print(
            Text.assemble(
                (f"{gb(summary['size_freed_bytes'])} freed", "green"),
                (f" · {summary['cleanup_warnings']} cleanup warnings", "yellow")
                if summary["cleanup_warnings"]
                else "",
            )
        )
    effects_by_rules: dict[tuple[str, ...], list[str]] = {}
    for rule in rules:
        effects = tuple(rule["related_changes"])
        if rule["match_count"] and effects:
            effects_by_rules.setdefault(effects, []).append(rule["name"])
    matching_rules = sum(bool(rule["match_count"]) for rule in rules)
    for effects, names in effects_by_rules.items():
        scope = f" ({', '.join(names)})" if len(names) < matching_rules else ""
        console.print(Text(f"On execution{scope} · " + "; ".join(effects)))
    for rule in rules:
        for warning in rule.get("warnings", []):
            console.print(Text(warning, style="yellow"))
        if rule["matches"] and rule["queue_effect"]:
            console.print(Text(f"{rule['name']} · On queueing  {rule['queue_effect']}"))
        if rule["dropped"]:
            console.print(Text("Dropped from queue: " + ", ".join(rule["dropped"])))
        if diagnostics:
            details = rule["diagnostics"]
            for label, (hits, unknown) in details["condition_counts"].items():
                console.print(Text(f"  {label} ({hits} matched, {unknown} unknown)"))
            if details["unknown_breakdown"].keys() - {UnknownReason.OTHER}:
                console.print(Text("  Unknown reasons", style="yellow"))
                for reason, count in details["unknown_breakdown"].items():
                    console.print(Text(f"    {count} {reason}"))
    matches = [row for rule in rules for row in rule["matches"]]
    if dry_run or matches:
        console.print()
    if matches:
        console.print(
            match_details(matches, show_all=show_all, preview=dry_run, rule_styles=rule_styles)
        )


def print_queue(rows: list[dict], console: Console) -> None:
    heading(console, "Queue")
    if not rows:
        console.print("No queued titles.")
        return
    compact = console.width < 100
    table = report_table(
        "Due (UTC)",
        "Title",
        "Size",
        *(("Action / rule",) if compact else ("Rule", "Planned action")),
        "Match evidence",
        "Key",
    )
    for row in rows:
        action = row["planned_action"]
        rule = row["rule"]
        cells(
            table,
            [
                Text(_at(row["due_at"]), style="yellow"),
                row["title"],
                gb(row["size_bytes"]),
                *((f"{action}\n{rule}",) if compact else (rule, action)),
                evidence_text(row["evidence"]),
                row["item_key"],
            ],
        )
    console.print(table)


def print_history(rows: list[dict], console: Console) -> None:
    heading(console, "History")
    if not rows:
        console.print("No actions recorded.")
        return
    compact = console.width < 100
    table = report_table(
        "At (UTC)",
        "Title",
        *(("Disk", "Action / rule") if compact else ("Size", "Freed", "Action", "Rule")),
        "Match evidence",
        "Result",
        *(() if compact else ("Details",)),
    )
    for row in rows:
        label, style = OUTCOMES[row["status"]]
        details = " · ".join(filter(None, [row["detail"], *(row["side_effect_errors"] or [])]))
        size = gb(row["size_bytes"]) if row["size_bytes"] is not None else "—"
        freed = gb(row["size_freed"])
        action = row["action"].replace("_", " ").capitalize()
        status = Text(label, style=style)
        if compact and details:
            status.append(f"\n{details}", style="default")
        cells(
            table,
            [
                Text(_at(row["at"]), style="cyan"),
                row["title"],
                *(
                    (f"Item {size}\nFreed {freed}", f"{action}\n{row['rule']}")
                    if compact
                    else (size, freed, action, row["rule"])
                ),
                evidence_text(row["evidence"]),
                status,
                *(() if compact else (details or "—",)),
            ],
        )
    console.print(table)


def print_rows(title: str, columns: dict[str, str], rows: list[dict], console: Console) -> None:
    heading(console, title)
    if not rows:
        console.print("No entries.")
        return
    table = report_table(*columns.values())
    for row in rows:
        cells(table, [row[key] for key in columns])
    console.print(table)


def print_rating_keys_prune(doc: dict, console: Console) -> None:
    heading(console, f"Removed {doc['summary']['removed']} known rating keys")


def print_cache(doc: dict, console: Console) -> None:
    rows = []
    for group in doc["items"]:
        age = group["oldest_age_seconds"]
        rows.append(
            group
            | {
                "age": _duration(age) if age is not None else "—",
                "next_expiry_at": _at(group["next_expiry_at"]),
                "due": Text(str(group["due"]), style="yellow" if group["due"] else "dim"),
            }
        )
    print_rows(
        "Cache status",
        {
            "type": "JustWatch data",
            "entries": "Entries",
            "age": "Oldest known age",
            "next_expiry_at": "Next expiry (UTC)",
            "due": "Due",
        },
        rows,
        console,
    )
    if any(group["due"] for group in doc["items"]):
        console.print("Due entries refresh when next used.", style="dim")
    if any(group["age_unavailable"] for group in doc["items"]):
        console.print("Fetch time is unavailable for some entries until refreshed.", style="dim")
    if "diagnostics" in doc:
        console.print()
        print_rows(
            "Cache entries",
            {"key": "Key", "fetched_at": "Fetched (UTC)", "expires_at": "Expires (UTC)"},
            [
                entry
                | {"fetched_at": _at(entry["fetched_at"]), "expires_at": _at(entry["expires_at"])}
                for entry in doc["diagnostics"]["entries"]
            ],
            console,
        )


def print_feed_endpoints(config, host: str, port: int, console: Console) -> None:
    print_rows(
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
        console,
    )
    console.print(
        "Append ?apikey=<API_KEY> to each URL using your list_proxy.api_key.", markup=False
    )


def print_schedule(doc: dict, console: Console) -> None:
    from zoneinfo import ZoneInfo

    zone = ZoneInfo(doc["summary"]["timezone"])

    def local(value):
        return (
            datetime.fromisoformat(value).astimezone(zone).strftime("%Y-%m-%d %H:%M %z")
            if value
            else "—"
        )

    rows = []
    for item in doc["items"]:
        last = item["last_execution"] or {}
        outcome = last.get("outcome") or ("running" if last else "—")
        rows.append(
            item
            | {
                "next": local(item["next_due"]),
                "last": local(last.get("finished_at")),
                "outcome": Text(
                    outcome,
                    style={
                        "success": "green",
                        "warning": "yellow",
                        "failed": "red",
                        "interrupted": "yellow",
                    }.get(outcome, ""),
                ),
                "error": last.get("error") or "—",
            }
        )
    summary = doc["summary"]
    print_rows(
        f"Schedule · {summary['daemon']} · {summary['timezone']}",
        {
            "kind": "Kind",
            "name": "Name",
            "schedule": "Cron",
            "state": "State",
            "next": "Next run",
            "last": "Last finish",
            "outcome": "Outcome",
            "error": "Last error",
        },
        rows,
        console,
    )
