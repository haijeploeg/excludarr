"""Rich output for rule reports, queue, exceptions and history."""

from datetime import datetime

from rich.console import Console
from rich.markup import escape as esc
from rich.table import Table

from excludarr.engine import Match, RuleReport


def gb(n: int) -> str:
    return f"{n / 1024**3:.2f} GB"


def sort_matches(matches: list[Match], by: str | None) -> list[Match]:
    """Sort by title, size (largest first) or date added (oldest first); None keeps order."""
    if by == "title":
        return sorted(matches, key=lambda m: m.item.title.lower())
    if by == "size":
        return sorted(matches, key=lambda m: -m.item.size_bytes)
    if by == "date":
        return sorted(matches, key=lambda m: (m.item.added is None, m.item.added))
    return list(matches)


def _day(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")


def matches_table(matches: list[Match], numbered: bool = False) -> Table:
    t = Table(*(["#"] if numbered else []), "title", "size", "reasons")
    for n, m in enumerate(matches, 1):
        row = [esc(m.item.title), gb(m.item.size_bytes), esc("; ".join(m.reasons))]
        t.add_row(*([str(n)] if numbered else []), *row)
    return t


def print_report(report: RuleReport, sort: str | None = None, console: Console | None = None):
    c = console or Console()
    rule = report.rule
    mode = "PREVIEW" if rule.preview else f"AUTO, grace {rule.grace_period.days}d"
    c.print(f"\n{rule.name}  [{mode}]", markup=False, style="bold")
    counts = Table("condition", "matches", "unknown")
    for label, (hit, unk) in report.condition_counts.items():
        counts.add_row(esc(label), str(hit), str(unk))
    c.print(counts)
    matches = sort_matches(report.matches, sort)
    if matches:
        c.print(matches_table(matches))
    c.print(f"Total: {len(matches)} matches, {gb(sum(m.item.size_bytes for m in matches))}")
    if report.executed:
        t = Table("executed", "size", "result")
        for m, res in report.executed:
            t.add_row(
                esc(m.item.title),
                gb(res.size_freed),
                esc(("ok: " if res.ok else "FAILED: ") + res.detail),
            )
        c.print(t)
    if report.queued:
        t = Table("queued", "due")
        for m, due in report.queued:
            t.add_row(esc(m.item.title), _day(due))
        c.print(t)
    if report.pending:
        t = Table("pending", "due")
        for m, due in report.pending:
            unk = " (unknown — kept)" if m.item.key in report.unknown else ""
            t.add_row(esc(m.item.title + unk), _day(due))
        c.print(t)
    if report.dropped:
        c.print("Dropped from queue (no longer match): " + ", ".join(report.dropped), markup=False)


def print_queue(rows, console: Console | None = None) -> None:
    t = Table("rule", "key", "title", "size", "due")
    for q in rows:
        t.add_row(esc(q.rule), esc(q.item_key), esc(q.title), gb(q.size_bytes), _day(q.due_at))
    (console or Console()).print(t)


def print_exceptions(rows, console: Console | None = None) -> None:
    t = Table("rule", "key", "title", "added")
    for e in rows:
        t.add_row(esc(e.rule), esc(e.item_key), esc(e.title), _day(e.created_at))
    (console or Console()).print(t)


def print_history(rows, console: Console | None = None) -> None:
    t = Table("at", "rule", "title", "action", "freed", "ok", "detail")
    for h in rows:
        t.add_row(
            h.at.strftime("%Y-%m-%d %H:%M"), esc(h.rule), esc(h.title), h.action,
            gb(h.size_freed), "yes" if h.ok else "NO", esc(h.detail),
        )  # fmt: skip
    (console or Console()).print(t)
