"""Read-only predictions for the next run and estimated disk savings."""

from typing import TYPE_CHECKING

from excludarr.config import Rule

if TYPE_CHECKING:
    from excludarr.engine import Match, RuleReport
    from excludarr.facts import Context


def action_description(rule: Rule) -> str:
    unit = rule.target == "sonarr" and rule.level in ("season", "episode")
    match rule.action:
        case "delete" if not unit:
            description = f"Remove from {rule.target.capitalize()}"
            description += " and delete files" if rule.delete_files else "; keep files"
        case "delete" | "delete_files":
            description = "Delete files and disable monitoring"
        case "monitor":
            description = "Enable monitoring"
        case "unmonitor":
            description = "Disable monitoring"
        case "tag":
            description = f"Add tag '{rule.tag}'"
        case "import_exclusion":
            description = "Add import exclusion"
    if unit and rule.action in ("tag", "import_exclusion"):
        description += " to the parent series"
    if rule.action == "delete" and not unit and rule.import_exclusion:
        description += "; add import exclusion"
    if rule.action == "monitor" and rule.search:
        description += "; search for missing media"
    return description


def plan_matches(
    report: "RuleReport", ctx: "Context", removed: set[str], *, simulate_actions: bool = False
) -> None:
    rule = report.rule
    queue = ctx.repo.queue_for(rule.name)
    for match in report.matches:
        item = match.item
        series_key = f"sonarr:series:{item.arr_id}"
        season_key = f"sonarr:season:{item.arr_id}:{item.season}"
        if (
            item.key in removed
            or (item.kind != "movie" and series_key in removed)
            or (item.kind == "episode" and season_key in removed)
        ):
            match.next_step = "skip"
        elif rule.preview and not simulate_actions:
            match.next_step = "preview"
        elif not rule.grace_period:
            match.next_step = "execute"
        elif item.key not in queue:
            match.next_step = "queue"
            match.due_at = ctx.now + rule.grace_period
        else:
            match.due_at = queue[item.key].due_at
            match.next_step = "execute" if match.due_at <= ctx.now else "wait"
        if match.next_step == "execute" and rule.action in ("delete", "delete_files"):
            removed.add(series_key if item.kind == "series" else item.key)


def reclaimable_files(match: "Match") -> dict[tuple[str, int], int]:
    rule, item = match.rule, match.item
    deletes_files = rule.action == "delete_files" or (
        rule.action == "delete" and (rule.delete_files or item.kind in ("season", "episode"))
    )
    if not deletes_files or not item.has_file:
        return {}
    if item.kind == "movie":
        return {("radarr", item.arr_id): item.size_bytes}
    sizes = item.file_sizes or {
        episode.file_id: episode.size_bytes
        for episode in item.episodes
        if episode.file_id is not None
    }
    return {("sonarr", file_id): size for file_id, size in sizes.items()}


def estimated_savings(reports: list["RuleReport"]) -> tuple[int, int, int]:
    titles = set()
    now, later = {}, {}
    for report in reports:
        for match in report.matches:
            item = match.item
            titles.add((report.rule.target, item.arr_id))
            if match.next_step == "execute":
                now.update(reclaimable_files(match))
            elif match.next_step in ("queue", "wait"):
                later.update(reclaimable_files(match))
    return (
        len(titles),
        sum(now.values()),
        sum(size for key, size in later.items() if key not in now),
    )
