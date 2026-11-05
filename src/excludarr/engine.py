"""Run rules: preview, grace queue, exceptions and the Leaving Soon collection."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from excludarr.actions import ActionResult, execute
from excludarr.conditions import All, Any_, describe, evaluate, leaves
from excludarr.config import Rule
from excludarr.facts import Context
from excludarr.items import MediaItem, build_radarr_items, build_sonarr_items

log = logging.getLogger(__name__)

REMOVING = ("delete", "delete_files")


@dataclass
class Match:
    rule: Rule
    item: MediaItem
    reasons: list[str]


@dataclass
class RuleReport:
    rule: Rule
    matches: list[Match]
    condition_counts: dict[str, tuple[int, int]]
    executed: list[tuple[Match, ActionResult]] = field(default_factory=list)
    queued: list[tuple[Match, datetime]] = field(default_factory=list)
    pending: list[tuple[Match, datetime]] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    # Keys of items whose result is unknown: never acted on, but a queued row stays queued.
    unknown: set[str] = field(default_factory=set)


def _series_key(key: str) -> str:
    """The parent of an item key: a movie is its own parent, sonarr units map to the series."""
    kind, _, rest = key.partition(":")
    return key if kind == "radarr" else "sonarr:series:" + rest.split(":")[1]


def _combine(cond, values: list[bool | None]) -> bool | None:
    if not isinstance(cond, (All, Any_)):
        return values[0]
    decisive = isinstance(cond, Any_)
    if decisive in values:
        return decisive
    return None if None in values else not decisive


def provider_lists(rules: list[Rule]) -> list:
    """Every provider list (a list of names or "my_providers") used by `rules`."""
    return [
        leaf.params[0]
        for r in rules
        for c in [r.when, *r.unless]
        for leaf in leaves(c)
        if leaf.name == "streaming"
    ]


def evaluate_rule(
    rule: Rule, items: list[MediaItem], ctx: Context, skip_keys: set[str]
) -> RuleReport:
    children = rule.when.children if isinstance(rule.when, (All, Any_)) else [rule.when]
    labels = [describe(c) for c in children]
    counts = {label: [0, 0] for label in labels}
    skip = skip_keys | ctx.repo.exceptions_for(rule.name)
    matches, unknown = [], set()
    for item in items:
        season_key = f"sonarr:season:{item.arr_id}:{item.season}"
        if (
            item.key in skip
            or _series_key(item.key) in skip
            or (item.kind == "episode" and season_key in skip)
            # An empty season/episode has nothing to free: never a delete match.
            or (
                rule.action in REMOVING and item.kind in ("season", "episode") and not item.has_file
            )
        ):
            continue
        values = [evaluate(c, item, ctx) for c in children]
        for label, v in zip(labels, values, strict=True):
            counts[label][0] += v is True
            counts[label][1] += v is None
        result = _combine(rule.when, values)
        for u in rule.unless if result is True else ():
            v = evaluate(u, item, ctx)
            if v is True:
                result = False
                break
            if v is None:
                result = None
        if result is True:
            reasons = [lb for lb, v in zip(labels, values, strict=True) if v is True]
            matches.append(Match(rule, item, reasons))
        elif result is None:
            unknown.add(item.key)
    return RuleReport(rule, matches, {k: (t, u) for k, (t, u) in counts.items()}, unknown=unknown)


def _collection(ctx: Context, item: MediaItem | None, add: bool) -> None:
    if not ctx.clients.plex or item is None:
        return
    name = ctx.config.integrations.plex.leaving_soon_collection
    try:
        plex_item = ctx.plex_item(item)
        if plex_item is None:
            raise LookupError("not found in Plex")
        plex = ctx.clients.plex
        (plex.add_to_collection if add else plex.remove_from_collection)(plex_item, name)
    except Exception as e:  # noqa: BLE001 - the collection never blocks queueing or execution
        log.warning("Leaving Soon collection update failed for %s: %s", item.title, e)


def _uncollect(ctx: Context, item: MediaItem | None) -> None:
    """Remove from the collection unless another queue row still covers the same movie/show."""
    if item is not None and not any(
        _series_key(q.item_key) == _series_key(item.key) for q in ctx.repo.queue_all()
    ):
        _collection(ctx, item, add=False)


def run(
    ctx: Context,
    *,
    dry_run: bool,
    rule_filter: str | None = None,
    select: Callable[[RuleReport], list[Match]] | None = None,
    confirm: Callable[[list[Match]], bool] = lambda m: True,
) -> list[RuleReport]:
    built: dict[tuple[str, str], list[MediaItem]] = {}
    prefetched: set[tuple[str, str]] = set()

    def items_for(target: str, level: str) -> list[MediaItem]:
        if (target, level) not in built:
            if target == "radarr":
                built[target, level] = build_radarr_items(ctx.clients.radarr)
            else:
                built[target, level] = build_sonarr_items(ctx.clients.sonarr, level)
        return built[target, level]

    def find(key: str) -> MediaItem | None:
        target, kind = key.split(":")[:2]
        # ponytail: an item gone from the library is not uncollected; Plex drops it anyway.
        return next((i for i in items_for(target, kind) if i.key == key), None)

    rules = [r for r in ctx.config.rules if r.enabled and rule_filter in (None, r.name)]
    # Preflight: fail on bad provider names or unreachable arrs before anything acts.
    for providers in provider_lists(rules):
        ctx.provider_ids(providers)
    for r in rules:
        items_for(r.target, r.level)
    names = {r.name for r in ctx.config.rules}
    if not dry_run:
        orphans = [q for q in ctx.repo.queue_all() if q.rule not in names]
        for q in orphans:
            ctx.repo.queue_remove(q.rule, q.item_key)
        for q in orphans:
            _uncollect(ctx, find(q.item_key) if ctx.clients.plex else None)

    removed: set[str] = set()

    def act(rule: Rule, m: Match, report: RuleReport) -> bool:
        res = execute(rule, m.item, ctx)
        detail = res.detail
        if res.side_effect_errors:
            detail += "; side effects failed: " + "; ".join(res.side_effect_errors)
        ctx.repo.history_add(
            rule.name, m.item.key, m.item.title, rule.action, res.size_freed, res.ok, detail
        )
        report.executed.append((m, res))
        if res.ok and rule.action in REMOVING:
            removed.add(_series_key(m.item.key) if m.item.kind == "series" else m.item.key)
        return res.ok

    reports = []
    for rule in rules:
        items = items_for(rule.target, rule.level)
        uses_streaming = any(
            leaf.name == "streaming" for c in [rule.when, *rule.unless] for leaf in leaves(c)
        )
        if uses_streaming and (rule.target, rule.level) not in prefetched:
            ctx.prefetch_streaming(items)
            prefetched.add((rule.target, rule.level))
        report = evaluate_rule(rule, items, ctx, removed)
        reports.append(report)
        if dry_run or rule.preview:
            continue
        matches = select(report) if select else report.matches
        queue = ctx.repo.queue_for(rule.name)
        by_key = {i.key: i for i in items}

        def drop(key: str, title: str, rule=rule, by_key=by_key, report=report) -> None:
            ctx.repo.queue_remove(rule.name, key)
            _uncollect(ctx, by_key.get(key))
            report.dropped.append(title)

        if not rule.grace_period:
            # Rows left over from when this rule had a grace period.
            for key, q in queue.items():
                drop(key, q.title)
            if matches and confirm(matches):
                for m in matches:
                    act(rule, m, report)
            continue

        due = []
        for m in matches:
            q = queue.get(m.item.key)
            if q is None:
                due_at = ctx.now + rule.grace_period
                ctx.repo.queue_add(rule.name, m.item.key, m.item.title, m.item.size_bytes, due_at)
                report.queued.append((m, due_at))
                if rule.leaving_soon_collection:
                    _collection(ctx, m.item, add=True)
            elif q.due_at <= ctx.now:
                due.append(m)
            else:
                report.pending.append((m, q.due_at))
        if due and confirm(due):
            for m in due:
                if act(rule, m, report):
                    ctx.repo.queue_remove(rule.name, m.item.key)
                    _uncollect(ctx, m.item)
        # Unselected (interactive) items still match, so their rows stay queued.
        matched = {m.item.key for m in report.matches}
        for key, q in queue.items():
            if key in report.unknown:
                # Unknown never acts and never drops: it waits for a definite answer.
                report.pending.append((Match(rule, by_key[key], []), q.due_at))
            elif key not in matched:
                drop(key, q.title)
    return reports
