"""Explicit command projections shared by the table, JSON and YAML renderers."""

import json
from dataclasses import asdict
from enum import StrEnum
from typing import Any

import yaml

from excludarr.engine import Match, RuleReport
from excludarr.preview import action_description, estimated_savings


class OutputFormat(StrEnum):
    table = "table"
    json = "json"
    yaml = "yaml"


def document(command: str) -> dict[str, Any]:
    return {"command": command, "status": "ok", "summary": {}, "items": [], "errors": []}


def serialize(report: dict[str, Any], format: OutputFormat) -> str:
    if format == OutputFormat.json:
        return json.dumps(report, ensure_ascii=False, indent=2)
    return yaml.safe_dump(report, allow_unicode=True, sort_keys=False).rstrip()


def sort_matches(matches: list[Match], by: str | None) -> list[Match]:
    if by == "title":
        return sorted(matches, key=lambda m: m.item.title.casefold())
    if by == "size":
        return sorted(matches, key=lambda m: -m.item.size_bytes)
    if by == "date":
        return sorted(matches, key=lambda m: (m.item.added is None, m.item.added))
    return list(matches)


def match_row(match: Match) -> dict:
    item = match.item
    return {
        "key": item.key,
        "title": item.title,
        "media": item.kind,
        "ids": {"tmdb": item.tmdb_id, "imdb": item.imdb_id, "tvdb": item.tvdb_id},
        "size_bytes": item.size_bytes,
        "rule": match.rule.name,
        "action": action_description(match.rule),
        "evidence": [asdict(entry) for entry in match.evidence],
        "context": match.context,
        "next_step": match.next_step,
        "due_at": match.due_at.isoformat() if match.due_at else None,
    }


def run_document(
    reports: list[RuleReport], *, dry_run: bool, sort: str | None = None, diagnostics: bool = False
) -> dict[str, Any]:
    doc = document("preview" if dry_run else "run")
    titles, now, later = estimated_savings(reports)
    rules = []
    attempted = [result for report in reports for _, result in report.executed]
    doc["summary"] = {
        "unique_titles": titles,
        "matches": sum(len(report.matches) for report in reports),
        "estimated_now_bytes": now,
        "estimated_after_grace_bytes": later,
        "size_freed_bytes": sum(result.size_freed for result in attempted),
        "failed": sum(not result.ok for result in attempted),
        "cleanup_warnings": sum(bool(result.side_effect_errors) for result in attempted),
    }
    for report in reports:
        results = {m.item.key: result for m, result in report.executed}
        queued = {m.item.key for m, _ in report.queued}
        pending = {m.item.key for m, _ in report.pending}
        unresolved = [m for m, _ in report.pending if m.item.key in report.unknown]
        matches = []
        for match in sort_matches(report.matches + unresolved, sort):
            row = match_row(match)
            key = match.item.key
            outcome = None
            if key in results:
                result = results[key]
                status = action_status(result.ok, result.side_effect_errors)
                outcome = {
                    "status": status,
                    "detail": result.detail,
                    "size_freed_bytes": result.size_freed,
                    "side_effect_errors": result.side_effect_errors,
                }
            else:
                if key in report.skipped:
                    status = "skipped"
                elif key in report.declined:
                    status = "declined"
                elif key in queued:
                    status = "queued"
                elif key in pending:
                    status = "pending"
                    if key in report.unknown:
                        row["next_step"] = "wait"
                else:
                    status = "not_executed"
                if not dry_run and not report.rule.preview:
                    outcome = {"status": status}
            matches.append(row | {"outcome": outcome, "matched": key not in report.unknown})
        rule = {
            "name": report.rule.name,
            "media": report.rule.level,
            "preview_only": report.rule.preview,
            "grace_seconds": int(report.rule.grace_period.total_seconds()),
            "action": action_description(report.rule),
            "related_changes": report.side_effects,
            "queue_effect": report.queue_effect,
            "match_count": len(report.matches),
            "matched_size_bytes": sum(m.item.size_bytes for m in report.matches),
            "matches": matches,
            "dropped": report.dropped,
        }
        if diagnostics:
            rule["diagnostics"] = {
                "condition_counts": {k: list(v) for k, v in report.condition_counts.items()},
                "unknown_count": len(report.unknown),
                "unknown_breakdown": dict(report.unknown_breakdown),
            }
        rules.append(rule)
    doc["rules"] = rules
    if doc["summary"]["failed"]:
        doc["status"] = "error"
    elif any(report.declined for report in reports) and not (
        attempted or any(r.queued for r in reports)
    ):
        doc["status"] = "declined"
    return doc


def action_status(ok: bool, warnings: list[str] | None) -> str:
    if not ok:
        return "failed"
    return "done_with_warning" if warnings else "done"


def queue_rows(entries, rules) -> list[dict]:
    rows = []
    for entry in entries:
        rule = rules.get(entry.rule)
        if rule is None:
            action = "Rule missing"
        elif not rule.enabled:
            action = "Rule disabled"
        elif rule.preview:
            action = "Preview only"
        else:
            action = action_description(rule)
        rows.append(
            asdict(entry)
            | {
                "due_at": entry.due_at.isoformat(),
                "enqueued_at": entry.enqueued_at.isoformat(),
                "planned_action": action,
            }
        )
    return rows


def history_rows(entries) -> list[dict]:
    return [
        asdict(entry)
        | {
            "at": entry.at.isoformat(),
            "status": action_status(entry.ok, entry.side_effect_errors),
        }
        for entry in entries
    ]


def cache_status(entries, now, *, diagnostics: bool) -> dict:
    groups = []
    for prefix, name in (
        ("jw:providers:", "Providers"),
        ("jw:match:", "Title matches"),
        ("jw:offers:", "Offers"),
    ):
        group = [entry for entry in entries if entry.key.startswith(prefix)]
        oldest = min((e.fetched_at for e in group if e.fetched_at is not None), default=None)
        next_expiry = min((e.expires_at for e in group if e.expires_at > now), default=None)
        groups.append(
            {
                "type": name,
                "entries": len(group),
                "due": sum(e.expires_at <= now for e in group),
                "age_unavailable": sum(e.fetched_at is None for e in group),
                "oldest_fetched_at": oldest.isoformat() if oldest else None,
                "oldest_age_seconds": int((now - oldest).total_seconds()) if oldest else None,
                "earliest_expiry_at": min(e.expires_at for e in group).isoformat()
                if group
                else None,
                "next_expiry_at": next_expiry.isoformat() if next_expiry else None,
            }
        )
    result = {"items": groups, "summary": {"checked_at": now.isoformat()}}
    if diagnostics:
        result["diagnostics"] = {
            "entries": [
                {
                    "key": entry.key,
                    "fetched_at": entry.fetched_at.isoformat() if entry.fetched_at else None,
                    "expires_at": entry.expires_at.isoformat(),
                    "due": entry.expires_at <= now,
                }
                for entry in entries
            ]
        }
    return result
