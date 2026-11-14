"""Run rules: preview, grace queue, exceptions and the Leaving Soon collection."""

import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from excludarr.actions import ActionResult, execute
from excludarr.conditions import LEAVES, All, Any_, Evidence, describe, evaluate, leaves
from excludarr.config import Rule
from excludarr.diagnostics import safe_error
from excludarr.facts import Context
from excludarr.items import MediaItem, build_radarr_items, build_sonarr_items
from excludarr.preview import plan_matches

log = logging.getLogger(__name__)

REMOVING = ("delete", "delete_files")


@dataclass
class Match:
    rule: Rule
    item: MediaItem
    reasons: list[str]
    context: dict[str, Any] = field(default_factory=dict)
    next_step: str | None = None
    due_at: datetime | None = None
    evidence: list[Evidence] = field(default_factory=list)


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
    side_effects: list[str] = field(default_factory=list)
    queue_effect: str | None = None
    unknown_breakdown: Counter[str] = field(default_factory=Counter)
    skipped: set[str] = field(default_factory=set)
    declined: set[str] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)


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
    rule: Rule,
    items: list[MediaItem],
    ctx: Context,
    skip_keys: set[str],
    progress: Callable[[str, int, int | None], None] = lambda message, done, total: None,
    diagnostics: bool = False,
) -> RuleReport:
    children = rule.when.children if isinstance(rule.when, (All, Any_)) else [rule.when]
    labels = [describe(c) for c in children]
    counts = {label: [0, 0] for label in labels}
    skip = skip_keys | ctx.repo.exceptions_for(rule.name)
    matches, unknown = [], set()
    unknown_breakdown: Counter[str] = Counter()
    for done, item in enumerate(items):
        progress(f"Evaluating {rule.name}", done, len(items))
        season_key = f"sonarr:season:{item.arr_id}:{item.season}"
        if (
            item.key in skip
            or _series_key(item.key) in skip
            or (item.kind == "episode" and season_key in skip)
            # An empty season/episode has nothing to free: never a delete match.
            or (
                rule.action in REMOVING and item.kind in ("season", "episode") and not item.has_file
            )
            # No files and already unmonitored: deleting the files changes nothing.
            or (rule.action == "delete_files" and not item.has_file and not item.monitored)
        ):
            continue
        causes = set() if diagnostics else None
        proofs: list[list[Evidence]] = [[] for _ in children]
        values = [
            evaluate(c, item, ctx, unknown_reasons=causes, evidence=proof)
            for c, proof in zip(children, proofs, strict=True)
        ]
        for label, v in zip(labels, values, strict=True):
            counts[label][0] += v is True
            counts[label][1] += v is None
        result = _combine(rule.when, values)
        if result is True and causes is not None:
            causes.clear()
        for u in rule.unless if result is True else ():
            v = evaluate(u, item, ctx, unknown_reasons=causes)
            if v is True:
                result = False
                break
            if v is None:
                result = None
        if result is True:
            reasons = [lb for lb, v in zip(labels, values, strict=True) if v is True]
            proof = (
                proofs[values.index(True)]
                if isinstance(rule.when, Any_)
                else [entry for entries in proofs for entry in entries]
            )
            matches.append(Match(rule, item, reasons, evidence=proof))
        elif result is None:
            unknown.add(item.key)
            if causes:
                unknown_breakdown[" + ".join(sorted(causes))] += 1
    progress(f"Evaluating {rule.name}", len(items), len(items))
    return RuleReport(
        rule,
        matches,
        {k: (t, u) for k, (t, u) in counts.items()},
        unknown=unknown,
        unknown_breakdown=unknown_breakdown,
    )


def _collection(ctx: Context, item: MediaItem | None, add: bool) -> str | None:
    if not ctx.clients.plex or item is None:
        return
    name = ctx.config.integrations.plex.leaving_soon_collection
    try:
        plex = ctx.clients.plex
        plex_item = ctx.plex_item(item)
        if plex_item is not None and item.kind == "season":
            plex_item = plex.season(plex_item, item.season)
        elif plex_item is not None and item.kind == "episode":
            plex_item = plex.episode(plex_item, item.season, item.episode)
        if plex_item is None:
            raise LookupError("not found in Plex")
        (plex.add_to_collection if add else plex.remove_from_collection)(plex_item, name)
    except Exception as e:  # noqa: BLE001 - the collection never blocks queueing or execution
        message = safe_error(
            ctx.config,
            f"Leaving Soon collection update failed for {item.title}: {type(e).__name__}: {e}",
        )
        log.warning("%s", message)
        return message


def _uncollect(ctx: Context, item: MediaItem | None) -> str | None:
    """Remove from the collection unless another queue row still covers the same item."""
    if item is not None and not any(q.item_key == item.key for q in ctx.repo.queue_all()):
        return _collection(ctx, item, add=False)


def run(
    ctx: Context,
    *,
    dry_run: bool,
    diagnostics: bool = False,
    on_report: Callable[[RuleReport], None] | None = None,
    rule_filter: str | None = None,
    target_filter: str | None = None,
    rule_names: frozenset[str] | None = None,
    should_stop: Callable[[], bool] = lambda: False,
    on_rule_start: Callable[[Rule], None] | None = None,
    on_rule_complete: Callable[[RuleReport], None] | None = None,
    select: Callable[[RuleReport], list[Match]] | None = None,
    confirm: Callable[[list[Match]], bool] = lambda m: True,
    describe_matches: Callable[[list[Match]], None] = lambda matches: None,
    progress: Callable[[str, int, int | None], None] = lambda message, done, total: None,
) -> list[RuleReport]:
    if should_stop():
        return []
    built: dict[tuple[str, str], list[MediaItem]] = {}
    prefetched: set[tuple[str, str]] = set()

    def items_for(target: str, level: str) -> list[MediaItem]:
        if (target, level) not in built:
            progress(f"Loading {target.capitalize()} library", 0, None)
            if target == "radarr":
                built[target, level] = build_radarr_items(ctx.clients.radarr)
            else:
                built[target, level] = build_sonarr_items(ctx.clients.sonarr, level)
        return built[target, level]

    def find(key: str) -> MediaItem | None:
        target, kind = key.split(":")[:2]
        # ponytail: an item gone from the library is not uncollected; Plex drops it anyway.
        return next((i for i in items_for(target, kind) if i.key == key), None)

    rules = [
        r
        for r in ctx.config.rules
        if r.enabled
        and rule_filter in (None, r.name)
        and target_filter in (None, r.target)
        and (rule_names is None or r.name in rule_names)
    ]
    # Preflight: fail on bad provider names or unreachable arrs before anything acts.
    for providers in provider_lists(rules):
        progress("Loading streaming providers", 0, None)
        ctx.provider_ids(providers)
    for r in rules:
        items_for(r.target, r.level)
    if should_stop():
        return []
    # Scan Plex now: `unless` leaves may never evaluate, and the scan stores the rating keys.
    if ctx.clients.plex and ctx.clients.tautulli:
        uses_watch = any(
            "tautulli" in LEAVES[leaf.name].integrations
            for r in rules
            for c in [r.when, *r.unless]
            for leaf in leaves(c)
        )
        if uses_watch:
            progress("Loading Plex library", 0, None)
            ctx.plex_library()
    names = {r.name for r in ctx.config.rules}
    target_prefix = f"{target_filter}:" if target_filter else ""
    preflight_warnings = []
    if not dry_run:
        progress("Cleaning up the grace queue", 0, None)
        orphans = [
            q
            for q in ctx.repo.queue_all()
            if q.rule not in names and q.item_key.startswith(target_prefix)
        ]
        for q in orphans:
            ctx.repo.queue_remove(q.rule, q.item_key)
        for q in orphans:
            if warning := _uncollect(ctx, find(q.item_key) if ctx.clients.plex else None):
                preflight_warnings.append(warning)

    removed: set[str] = set()
    predicted_removed: set[str] = set()

    def act(rule: Rule, m: Match, report: RuleReport) -> bool:
        progress(f"Executing {rule.name}", 0, None)
        res = execute(rule, m.item, ctx)
        ctx.repo.history_add(
            rule.name,
            m.item.key,
            m.item.title,
            rule.action,
            res.size_freed,
            res.ok,
            res.detail,
            evidence=[asdict(entry) for entry in m.evidence],
            size_bytes=m.item.size_bytes,
            side_effect_errors=res.side_effect_errors,
        )
        report.executed.append((m, res))
        if res.ok and rule.action in REMOVING:
            removed.add(_series_key(m.item.key) if m.item.kind == "series" else m.item.key)
        return res.ok

    def execute_matches(rule, matches, report, *, from_queue=False):
        message = f"Executing {rule.name}"
        progress(message, 0, len(matches))
        for done, match in enumerate(matches, 1):
            if act(rule, match, report) and from_queue:
                ctx.repo.queue_remove(rule.name, match.item.key)
                if warning := _uncollect(ctx, match.item):
                    report.warnings.append(warning)
            progress(message, done, len(matches))

    reports = []
    for rule in rules:
        if should_stop():
            break
        if on_rule_start:
            on_rule_start(rule)
        items = items_for(rule.target, rule.level)
        uses_streaming = any(
            leaf.name == "streaming" for c in [rule.when, *rule.unless] for leaf in leaves(c)
        )
        if uses_streaming and (rule.target, rule.level) not in prefetched:
            ctx.prefetch_streaming(items, progress=progress)
            prefetched.add((rule.target, rule.level))
        report = evaluate_rule(
            rule, items, ctx, removed, progress=progress, diagnostics=diagnostics
        )
        report.warnings.extend(preflight_warnings)
        preflight_warnings.clear()
        reports.append(report)
        if on_report is not None:
            on_report(report)
        plan_matches(report, ctx, predicted_removed if dry_run else set(), simulate_actions=dry_run)
        if rule.action in REMOVING:
            report.side_effects.append("Clean up related download queue entries")
            if ctx.clients.seerr:
                report.side_effects.append("Clean up matching Seerr records after deletion")
            if ctx.clients.plex:
                report.side_effects.append("Refresh the Plex library")
        if rule.grace_period and rule.leaving_soon_collection and ctx.clients.plex:
            report.queue_effect = (
                f"Add to Plex collection '{ctx.config.integrations.plex.leaving_soon_collection}'"
            )
        describe_matches(report.matches)
        if dry_run or rule.preview:
            if on_rule_complete:
                on_rule_complete(report)
            continue
        matches = select(report) if select else report.matches
        if select:
            report.skipped = {m.item.key for m in report.matches} - {m.item.key for m in matches}
        progress(f"Updating queue for {rule.name}", 0, None)
        queue = {
            key: row
            for key, row in ctx.repo.queue_for(rule.name).items()
            if key.startswith(target_prefix)
        }
        by_key = {i.key: i for i in items}

        def drop(key: str, title: str, rule=rule, by_key=by_key, report=report) -> None:
            ctx.repo.queue_remove(rule.name, key)
            if warning := _uncollect(ctx, by_key.get(key)):
                report.warnings.append(warning)
            report.dropped.append(title)

        if not rule.grace_period:
            # Rows left over from when this rule had a grace period.
            for key, q in queue.items():
                drop(key, q.title)
            if matches:
                if confirm(matches):
                    execute_matches(rule, matches, report)
                else:
                    report.declined.update(m.item.key for m in matches)
            if on_rule_complete:
                on_rule_complete(report)
            continue

        due = []
        for m in matches:
            q = queue.get(m.item.key)
            if q is None:
                due_at = ctx.now + rule.grace_period
                ctx.repo.queue_add(
                    rule.name,
                    m.item.key,
                    m.item.title,
                    m.item.size_bytes,
                    due_at,
                    evidence=[asdict(entry) for entry in m.evidence],
                )
                report.queued.append((m, due_at))
                if rule.leaving_soon_collection and (warning := _collection(ctx, m.item, add=True)):
                    report.warnings.append(warning)
            elif q.due_at <= ctx.now:
                due.append(m)
            else:
                report.pending.append((m, q.due_at))
        if due:
            if confirm(due):
                execute_matches(rule, due, report, from_queue=True)
            else:
                report.declined.update(m.item.key for m in due)
        # Unselected (interactive) items still match, so their rows stay queued.
        matched = {m.item.key for m in report.matches}
        for key, q in queue.items():
            if key in report.unknown:
                # Unknown never acts and never drops: it waits for a definite answer.
                report.pending.append((Match(rule, by_key[key], [], due_at=q.due_at), q.due_at))
            elif key not in matched:
                drop(key, q.title)
        describe_matches([m for m, _ in report.pending if m.item.key in report.unknown])
        if on_rule_complete:
            on_rule_complete(report)
    return reports
