"""Execute a rule's action on one item, plus the side effects of deleting."""

from dataclasses import dataclass, field

from excludarr.config import Rule
from excludarr.facts import Context
from excludarr.items import MediaItem


@dataclass
class ActionResult:
    ok: bool
    size_freed: int
    detail: str
    side_effect_errors: list[str] = field(default_factory=list)


def _with_season(raw: dict, n: int, monitored: bool) -> dict:
    seasons = [
        {**s, "monitored": monitored} if s["seasonNumber"] == n else s
        for s in raw.get("seasons", [])
    ]
    return {**raw, "seasons": seasons}


def _add_tag(cur: dict, tag_id: int) -> dict | None:
    tags = cur.get("tags", [])
    return None if tag_id in tags else {**cur, "tags": [*tags, tag_id]}


# Updates always start from the current object, never the build-time `item.raw`
# snapshot: several items (or rules) can touch one movie/series in a single run.
def _radarr(rule: Rule, item: MediaItem, ctx: Context) -> tuple[int, str]:
    radarr, mid = ctx.clients.radarr, item.arr_id

    def update(**changes):
        radarr.update_movie({**radarr.get_movie(mid), **changes})

    match rule.action:
        case "delete":
            radarr.delete_movie(item.arr_id, rule.delete_files, rule.import_exclusion)
            return (item.size_bytes if rule.delete_files else 0), "deleted movie"
        case "delete_files":
            ids = [f["id"] for f in radarr.movie_files(item.arr_id)]
            if ids:
                radarr.delete_movie_files(ids)
            update(monitored=False)
            return (item.size_bytes if ids else 0), f"deleted {len(ids)} file(s), unmonitored"
        case "unmonitor" | "monitor":
            update(monitored=rule.action == "monitor")
            if rule.action == "monitor" and rule.search:
                radarr.search([item.arr_id])
            return 0, f"{rule.action}ed"
        case "tag":
            if tagged := _add_tag(radarr.get_movie(mid), radarr.ensure_tag(rule.tag)):
                radarr.update_movie(tagged)
            return 0, f"tagged {rule.tag!r}"
        case "import_exclusion":
            radarr.add_exclusion(item.tmdb_id, item.base_title, item.year)
            return 0, "added import exclusion"
    raise ValueError(f"unknown action {rule.action!r}")


def _sonarr(rule: Rule, item: MediaItem, ctx: Context) -> tuple[int, str]:
    sonarr, sid, action = ctx.clients.sonarr, item.arr_id, rule.action

    def current() -> dict:
        return sonarr.get_series_by_id(sid)

    # tag and import_exclusion always apply to the parent series.
    if action == "tag":
        if tagged := _add_tag(current(), sonarr.ensure_tag(rule.tag)):
            sonarr.update_series(tagged)
        return 0, f"tagged {rule.tag!r}"
    if action == "import_exclusion":
        sonarr.add_exclusion(item.tvdb_id, item.base_title)
        return 0, "added import exclusion"
    if item.kind == "series":
        if action == "delete":
            sonarr.delete_series(sid, rule.delete_files, rule.import_exclusion)
            return (item.size_bytes if rule.delete_files else 0), "deleted series"
        if action == "delete_files":
            ids = [f["id"] for f in sonarr.episode_files(sid)]
            if ids:
                sonarr.delete_episode_files(ids)
            sonarr.update_series({**current(), "monitored": False})
            return (item.size_bytes if ids else 0), f"deleted {len(ids)} file(s), unmonitored"
        sonarr.update_series({**current(), "monitored": action == "monitor"})
        if action == "monitor" and rule.search:
            sonarr.search(sid)
        return 0, f"{action}ed"
    ep_ids = [e.id for e in item.episodes]
    if action in ("delete", "delete_files"):
        # ponytail: a multi-episode file shared with episodes outside the unit is deleted
        # too; handle it if someone runs episode-level deletes on multi-episode files.
        file_ids = sorted({e.file_id for e in item.episodes if e.file_id is not None})
        if file_ids:
            sonarr.delete_episode_files(file_ids)
        sonarr.set_episodes_monitored(ep_ids, False)
        if item.kind == "season":
            sonarr.update_series(_with_season(current(), item.season, False))
        freed = item.size_bytes if file_ids else 0
        return freed, f"deleted {len(file_ids)} file(s), unmonitored"
    monitored = action == "monitor"
    if item.kind == "season":
        sonarr.update_series(_with_season(current(), item.season, monitored))
        sonarr.set_episodes_monitored(ep_ids, monitored)
        if monitored and rule.search:
            sonarr.search(sid, season=item.season)
    else:
        sonarr.set_episodes_monitored(ep_ids, monitored)
        if monitored and rule.search:
            sonarr.search(sid, episode_ids=ep_ids)
    return 0, f"{action}ed"


def _clean_queue(item: MediaItem, ctx: Context) -> None:
    if item.kind == "movie":
        arr = ctx.clients.radarr
        hits = [r for r in arr.queue() if r.get("movieId") == item.arr_id]
    else:
        arr = ctx.clients.sonarr
        ep_ids = {e.id for e in item.episodes}
        hits = [
            r
            for r in arr.queue()
            if r.get("seriesId") == item.arr_id
            and (item.kind == "series" or r.get("episodeId") in ep_ids)
        ]
    for r in hits:
        arr.remove_queue_item(r["id"])


def _clean_seerr(item: MediaItem, ctx: Context) -> None:
    seerr = ctx.clients.seerr
    if not seerr:
        return
    reqs = ctx.requests(item)
    if reqs is None:
        raise RuntimeError("requests unavailable")
    if item.kind in ("movie", "series"):
        for media_id in sorted({r.media_id for r in reqs}):
            seerr.delete_media(media_id)
        return
    with_files = {f["seasonNumber"] for f in ctx.clients.sonarr.episode_files(item.arr_id)}
    for r in reqs:
        if not r.seasons & with_files:
            seerr.delete_request(r.id)


def _refresh_plex(item: MediaItem, ctx: Context) -> None:
    plex_item = ctx.plex_item(item)
    if plex_item:
        ctx.clients.plex.refresh(plex_item.section_key)


SIDE_EFFECTS = {"queue": _clean_queue, "seerr": _clean_seerr, "plex": _refresh_plex}


def execute(rule: Rule, item: MediaItem, ctx: Context) -> ActionResult:
    target = "radarr" if item.kind == "movie" else "sonarr"
    if getattr(ctx.clients, target) is None:
        return ActionResult(False, 0, f"{target} not configured")
    try:
        main = _radarr if item.kind == "movie" else _sonarr
        freed, detail = main(rule, item, ctx)
    except Exception as e:  # noqa: BLE001 - a failed action is reported, never raised
        return ActionResult(False, 0, str(e))
    errors = []
    if rule.action in ("delete", "delete_files"):
        for name, step in SIDE_EFFECTS.items():
            try:
                step(item, ctx)
            except Exception as e:  # noqa: BLE001 - side effects never roll back the action
                errors.append(f"{name}: {e}")
    return ActionResult(True, freed, detail, errors)
