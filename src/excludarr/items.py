"""Library item model shared by facts, rules and builders."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from excludarr.clients.radarr import RadarrClient
from excludarr.clients.sonarr import SonarrClient


@dataclass(frozen=True)
class EpisodeRef:
    id: int
    season: int
    number: int
    aired: bool
    file_id: int | None
    size_bytes: int
    monitored: bool


@dataclass
class MediaItem:
    key: str
    kind: Literal["movie", "series", "season", "episode"]
    title: str
    base_title: str
    arr_id: int
    season: int | None = None
    episode: int | None = None
    tmdb_id: int | None = None
    imdb_id: str | None = None
    tvdb_id: int | None = None
    year: int | None = None
    added: datetime | None = None
    size_bytes: int = 0
    has_file: bool = False
    monitored: bool = True
    tags: frozenset[str] = frozenset()
    genres: frozenset[str] = frozenset()
    ratings: dict[str, float] = field(default_factory=dict)
    ended: bool | None = None
    rank_from_latest: int | None = None
    episodes: tuple[EpisodeRef, ...] = ()
    raw: dict = field(default_factory=dict)
    file_sizes: dict[int, int] = field(default_factory=dict)
    file_added_at: datetime | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _dt(s: str | None) -> datetime | None:
    if not s:
        return None
    date = datetime.fromisoformat(s)
    return date.replace(tzinfo=UTC) if date.tzinfo is None else date.astimezone(UTC)


def _ids(d: dict) -> dict:
    return {
        "tmdb_id": d.get("tmdbId") or None,
        "imdb_id": d.get("imdbId") or None,
        "tvdb_id": d.get("tvdbId") or None,
    }


def _ratings(pairs: dict[str, float | None]) -> dict[str, float]:
    return {k: v for k, v in pairs.items() if v}


def build_radarr_items(radarr: RadarrClient) -> list[MediaItem]:
    tags = radarr.tags()
    items = []
    for m in radarr.movies():
        r = m.get("ratings") or {}
        items.append(
            MediaItem(
                key=f"radarr:movie:{m['id']}",
                kind="movie",
                title=f"{m['title']} ({m['year']})",
                base_title=m["title"],
                arr_id=m["id"],
                year=m.get("year") or None,
                added=_dt(m.get("added")),
                file_added_at=_dt((m.get("movieFile") or {}).get("dateAdded")),
                size_bytes=m.get("sizeOnDisk") or 0,
                has_file=bool(m.get("hasFile")),
                monitored=bool(m.get("monitored")),
                tags=frozenset(tags[t] for t in m.get("tags", []) if t in tags),
                genres=frozenset(m.get("genres", [])),
                ratings=_ratings(
                    {
                        "tmdb": (r.get("tmdb") or {}).get("value"),
                        "imdb": (r.get("imdb") or {}).get("value"),
                    }
                ),
                raw=m,
                **_ids(m),
            )
        )
    return items


def build_sonarr_items(
    sonarr: SonarrClient, level: Literal["series", "season", "episode"]
) -> list[MediaItem]:
    tags = sonarr.tags()
    now = _now()
    items: list[MediaItem] = []
    for s in sonarr.series():
        sid = s["id"]
        files = sonarr.episode_files(sid)
        sizes = {f["id"]: f.get("size") or 0 for f in files}
        file_added = {f["id"]: _dt(f.get("dateAdded")) for f in files}
        eps = sorted(sonarr.episodes(sid), key=lambda e: (e["seasonNumber"], e["episodeNumber"]))
        refs = [
            (
                e,
                EpisodeRef(
                    id=e["id"],
                    season=e["seasonNumber"],
                    number=e["episodeNumber"],
                    aired=(d := _dt(e.get("airDateUtc"))) is not None and d <= now,
                    file_id=e.get("episodeFileId") or None,
                    size_bytes=sizes.get(e.get("episodeFileId") or 0, 0),
                    monitored=bool(e.get("monitored")),
                ),
            )
            for e in eps
        ]
        base = s["title"]
        common = dict(
            base_title=base,
            arr_id=sid,
            year=s.get("year") or None,
            added=_dt(s.get("added")),
            tags=frozenset(tags[t] for t in s.get("tags", []) if t in tags),
            genres=frozenset(s.get("genres", [])),
            ratings=_ratings({"sonarr": (s.get("ratings") or {}).get("value")}),
            ended=s.get("status") == "ended",
            raw=s,
            **_ids(s),
        )
        real = [r for _, r in refs if r.season != 0]

        def unit(
            key, kind, title, unit_refs, monitored, common=common, file_added=file_added, **kw
        ):
            dates = [d for r in unit_refs if (d := file_added.get(r.file_id))]
            if kind != "series":
                # A season/episode was added when its newest file landed; no files: the series.
                common = common | {"added": max(dates, default=common["added"])}
            return MediaItem(
                key=key,
                kind=kind,
                title=title,
                size_bytes=sum(r.size_bytes for r in unit_refs),
                has_file=any(r.file_id for r in unit_refs),
                monitored=monitored,
                episodes=tuple(unit_refs),
                file_sizes={r.file_id: r.size_bytes for r in unit_refs if r.file_id is not None},
                file_added_at=max(dates, default=None),
                **common,
                **kw,
            )

        if level == "series":
            it = unit(
                f"sonarr:series:{sid}",
                "series",
                f"{base} ({s['year']})",
                real,
                bool(s.get("monitored")),
            )
            # ponytail: series size counts all files incl. specials
            it.size_bytes = sum(sizes.values())
            it.has_file = bool(sizes)
            it.file_sizes = sizes
            it.file_added_at = max((d for d in file_added.values() if d is not None), default=None)
            items.append(it)
        elif level == "season":
            flags = {x["seasonNumber"]: bool(x.get("monitored")) for x in s.get("seasons", [])}
            nums = sorted({r.season for r in real})
            aired = [n for n in nums if any(r.aired for r in real if r.season == n)]
            for n in nums:
                ur = [r for r in real if r.season == n]
                items.append(
                    unit(
                        f"sonarr:season:{sid}:{n}",
                        "season",
                        f"{base} – S{n:02d}",
                        ur,
                        flags.get(n, any(r.monitored for r in ur)),
                        season=n,
                        rank_from_latest=aired[::-1].index(n) if n in aired else None,
                    )
                )
        else:
            aired = [r for r in real if r.aired]
            for r in real:
                items.append(
                    unit(
                        f"sonarr:episode:{sid}:{r.season}:{r.number}",
                        "episode",
                        f"{base} – S{r.season:02d}E{r.number:02d}",
                        [r],
                        r.monitored,
                        season=r.season,
                        episode=r.number,
                        rank_from_latest=aired[::-1].index(r) if r in aired else None,
                    )
                )
    return items
