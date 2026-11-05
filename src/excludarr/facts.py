"""Facts about library items, looked up lazily from integrations."""

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

import httpx

from excludarr.clients.http import IntegrationError
from excludarr.clients.justwatch import Avail, JustWatchClient, Provider
from excludarr.clients.plex import PlexClient, PlexItem
from excludarr.clients.radarr import RadarrClient
from excludarr.clients.seerr import SeerrClient, SeerrRequest
from excludarr.clients.sonarr import SonarrClient
from excludarr.clients.tautulli import TautulliClient
from excludarr.config import Config, ConfigError
from excludarr.items import MediaItem
from excludarr.storage.repo import Repo

log = logging.getLogger(__name__)

WEEK = timedelta(days=7)
DAY = timedelta(days=1)


@dataclass
class Clients:
    radarr: RadarrClient | None = None
    sonarr: SonarrClient | None = None
    justwatch: JustWatchClient | None = None
    tautulli: TautulliClient | None = None
    plex: PlexClient | None = None
    seerr: SeerrClient | None = None

    @classmethod
    def from_config(cls, config: Config) -> "Clients":
        i = config.integrations
        return cls(
            radarr=RadarrClient(i.radarr) if i.radarr else None,
            sonarr=SonarrClient(i.sonarr) if i.sonarr else None,
            justwatch=JustWatchClient(config.profile.locale),
            tautulli=TautulliClient(i.tautulli) if i.tautulli else None,
            plex=PlexClient(i.plex) if i.plex else None,
            seerr=SeerrClient(i.seerr) if i.seerr else None,
        )


@dataclass
class WatchStats:
    last_watched: datetime | None
    play_count: int
    fully_watched: bool
    last_by_user: dict[str, datetime]


class Context:
    def __init__(self, config: Config, clients: Clients, repo: Repo, now: datetime):
        self.config = config
        self.clients = clients
        self.repo = repo
        self.now = now
        self._memo: dict[Any, Any] = {}
        self._failed: set[str] = set()

    # --- providers -------------------------------------------------------
    def _providers(self) -> list[Provider]:
        jw = self.clients.justwatch
        key = f"jw:providers:{jw.locale}"
        cached = self.repo.cache_get(key)
        if cached is None:
            cached = [vars(p) for p in jw.providers()]
            self.repo.cache_set(key, cached, WEEK)
        return [Provider(**p) for p in cached]

    def provider_ids(self, names: list[str] | Literal["my_providers"]) -> set[int]:
        if names == "my_providers":
            names = self.config.profile.providers
        memo_key = ("providers", *names)
        if memo_key not in self._memo:
            self._memo[memo_key] = self._resolve_providers(names)
        return self._memo[memo_key]

    def _resolve_providers(self, names: list[str]) -> set[int]:
        by_name = {p.clear_name.lower(): p.id for p in self._providers()}
        ids = set()
        for n in names:
            if n.lower() not in by_name:
                raise ConfigError(
                    f"unknown provider '{n}' for locale {self.clients.justwatch.locale}; "
                    "see `excludarr providers list`"
                )
            ids.add(by_name[n.lower()])
        return ids

    # --- streaming -------------------------------------------------------
    def _match(self, item: MediaItem, kind: Literal["MOVIE", "SHOW"]) -> str | None:
        ident = item.tmdb_id or item.imdb_id
        if not ident:
            return None
        key = f"jw:match:{kind}:{ident}"
        node_id = self.repo.cache_get(key)
        if node_id is None:
            node_id = ""
            for r in self.clients.justwatch.search(item.base_title, kind):
                if (item.tmdb_id and r.tmdb_id == item.tmdb_id) or (
                    item.imdb_id and r.imdb_id == item.imdb_id
                ):
                    node_id = r.node_id
                    break
            self.repo.cache_set(key, node_id, WEEK)
        return node_id or None

    def _offers(self, node_id: str, kind: Literal["MOVIE", "SHOW"]) -> dict[tuple[int, int], Avail]:
        """Offers per (season, episode); a movie is stored under (0, 0)."""
        key = f"jw:offers:{node_id}"
        cached = self.repo.cache_get(key)
        if cached is None:
            jw = self.clients.justwatch
            if kind == "MOVIE":
                offers = {(0, 0): jw.movie_offers(node_id)}
            else:
                offers = jw.show_offers(node_id)
            cached = [[s, e, sorted(a)] for (s, e), a in offers.items()]
            self.repo.cache_set(key, cached, DAY)
        return {(s, e): frozenset((p, m) for p, m in a) for s, e, a in cached}

    def streaming(self, item: MediaItem) -> list[Avail] | None:
        """One Avail per atomic unit; [] means "no aired units", None means unknown."""
        if "justwatch" in self._failed:
            return None
        memo_key = ("streaming", item.key)
        if memo_key not in self._memo:
            self._memo[memo_key] = self._streaming(item)
        return self._memo[memo_key]

    def _streaming(self, item: MediaItem) -> list[Avail] | None:
        kind = "MOVIE" if item.kind == "movie" else "SHOW"
        try:
            node_id = self._match(item, kind)
            if node_id is None:
                return None
            offers = self._offers(node_id, kind)
        except IntegrationError as e:
            # Transport failure or server error: JustWatch is down, stop asking this run.
            # (status None alone is not enough: GraphQL/shape errors also carry None.)
            if isinstance(e.__cause__, httpx.TransportError) or (e.status or 0) >= 500:
                if "justwatch" not in self._failed:
                    self._failed.add("justwatch")
                    log.warning("JustWatch unavailable, streaming is unknown this run: %s", e)
                return None
            log.warning("JustWatch lookup failed for %s: %s", item.title, e)
            return None
        except Exception as e:  # noqa: BLE001 - one bad title must never abort a run
            log.warning("JustWatch lookup failed for %s: %s", item.title, e)
            return None
        if item.kind == "movie":
            return [offers.get((0, 0), frozenset())]
        if item.kind == "episode":
            units = [(item.season, item.episode)]
        else:
            units = [
                (e.season, e.number)
                for e in item.episodes
                if e.aired and (e.season == item.season if item.kind == "season" else e.season >= 1)
            ]
        return [offers.get(u, frozenset()) for u in units]

    def prefetch_streaming(self, items: list[MediaItem]) -> None:
        distinct = {(i.kind == "movie", i.tmdb_id, i.imdb_id): i for i in items}
        with ThreadPoolExecutor(max_workers=4) as pool:
            # streaming() never raises for lookup failures, so results can be dropped.
            list(pool.map(self.streaming, distinct.values()))

    # --- watch / requests ------------------------------------------------
    def _once(self, name: str, fetch) -> Any | None:
        """Fetch at most once per run; any failure marks `name` failed (one warning)."""
        if name in self._failed:
            return None
        if name not in self._memo:
            try:
                self._memo[name] = fetch()
            except Exception as e:  # noqa: BLE001 - unknown, never an action
                log.warning("%s unavailable, its conditions are unknown this run: %s", name, e)
                self._failed.add(name)
                return None
        return self._memo[name]

    def plex_item(self, item: MediaItem) -> PlexItem | None:
        if not self.clients.plex:
            return None
        by_guid = self._once("plex", self.clients.plex.items_by_guid)
        if by_guid is None:
            return None
        kind = "movie" if item.kind == "movie" else "show"
        for prefix, ident in (
            ("tmdb", item.tmdb_id),
            ("imdb", item.imdb_id),
            ("tvdb", item.tvdb_id),
        ):
            if ident and (kind, f"{prefix}://{ident}") in by_guid:
                return by_guid[(kind, f"{prefix}://{ident}")]
        return None

    def watch(self, item: MediaItem) -> WatchStats | None:
        if not (self.clients.tautulli and self.clients.plex):
            return None
        units = {
            (e.season, e.number)
            for e in item.episodes
            if e.aired and (e.season >= 1 if item.kind == "series" else e.season == item.season)
        }
        if item.kind != "movie" and not units:
            return None  # nothing aired: nothing to watch, so watch facts are unknown
        plex_item = self.plex_item(item)
        history = self._once("tautulli", self.clients.tautulli.history)
        if plex_item is None or history is None:
            return None
        if item.kind == "movie":
            rows = [r for r in history if r.rating_key == plex_item.rating_key]
        else:
            rows = [
                r
                for r in history
                if r.grandparent_rating_key == plex_item.rating_key
                and (item.season is None or r.season == item.season)
                and (item.episode is None or r.episode == item.episode)
                and (item.kind != "series" or r.season != 0)  # ponytail: specials ignored
            ]
        watched = [r for r in rows if r.watched]
        full = (
            bool(watched)
            if item.kind == "movie"
            else units <= {(r.season, r.episode) for r in watched}
        )
        last_by_user: dict[str, datetime] = {}
        for r in watched:
            for name in filter(None, (r.user.lower(), r.friendly_name.lower())):
                if name not in last_by_user or r.at > last_by_user[name]:
                    last_by_user[name] = r.at
        return WatchStats(
            last_watched=max((r.at for r in rows), default=None),
            play_count=len(watched),
            fully_watched=full,
            last_by_user=last_by_user,
        )

    def requests(self, item: MediaItem) -> list[SeerrRequest] | None:
        if not self.clients.seerr:
            return None
        allreq = self._once("seerr", self.clients.seerr.requests)
        if allreq is None:
            return None
        out = []
        for r in allreq:
            if item.kind == "movie":
                ok = r.media_type == "movie" and bool(item.tmdb_id) and r.tmdb_id == item.tmdb_id
            else:
                ok = r.media_type == "tv" and (
                    (item.tmdb_id and r.tmdb_id == item.tmdb_id)
                    or (item.tvdb_id and r.tvdb_id == item.tvdb_id)
                )
            if ok and item.kind in ("season", "episode"):
                ok = item.season in r.seasons
            if ok:
                out.append(r)
        return out
