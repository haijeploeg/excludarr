"""Facts about library items, looked up lazily from integrations."""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Lock
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
from excludarr.lists.items import ListItem
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

    def close(self) -> None:
        from excludarr.clients.http import HttpClient

        for client in vars(self).values():
            http = getattr(client, "http", None)
            if isinstance(http, HttpClient):
                http.close()

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
    watched_users: list[str] = field(default_factory=list)


class Context:
    def __init__(
        self, config: Config, clients: Clients, repo: Repo, now: datetime, *, refresh: bool = False
    ):
        self.config = config
        self.clients = clients
        self.repo = repo
        self.now = now
        self.refresh = refresh
        self._cache_locks: dict[str, Lock] = {}
        self._memo: dict[Any, Any] = {}
        self._failed: set[str] = set()

    def _cached(self, key: str, fetch, ttl: timedelta, *, legacy_key: str | None = None) -> Any:
        # Different Sonarr units may share the same JustWatch lookup.
        with self._cache_locks.setdefault(key, Lock()):
            if key in self._memo:
                return self._memo[key]
            if not self.refresh:
                now = datetime.now(UTC)
                for candidate in (key, legacy_key):
                    if candidate is None:
                        continue
                    entry = self.repo.cache_entry(candidate)
                    if entry is None:
                        continue
                    fresh = entry.expires_at > now
                    log.debug(
                        "Cache %s %s (fetched %s; expires %s)",
                        "hit" if fresh else "expired",
                        candidate,
                        entry.fetched_at or "unavailable",
                        entry.expires_at,
                    )
                    if fresh and (candidate == key or entry.value):
                        self._memo[key] = entry.value
                        return entry.value
            log.debug("Cache %s %s", "forced refresh" if self.refresh else "fetch", key)
            value = fetch()
            self.repo.cache_set(key, value, ttl)
            if log.isEnabledFor(logging.DEBUG):
                entry = self.repo.cache_entry(key)
                if entry is not None:
                    log.debug(
                        "Cache stored %s (fetched %s; expires %s)",
                        key,
                        entry.fetched_at,
                        entry.expires_at,
                    )
            self._memo[key] = value
            return value

    # --- providers -------------------------------------------------------
    def _providers(self) -> list[Provider]:
        jw = self.clients.justwatch
        key = f"jw:providers:{jw.locale}"
        entries = self._cached(key, lambda: [vars(p) for p in jw.providers()], WEEK)
        return [Provider(**p) for p in entries]

    def provider_ids(self, names: list[str] | Literal["my_providers"]) -> set[int] | None:
        if names == "my_providers":
            names = self.config.profile.providers
        memo_key = ("providers", *names)
        if memo_key not in self._memo:
            self._memo[memo_key] = self._resolve_providers(names)
        return self._memo[memo_key]

    def _resolve_providers(self, names: list[str]) -> set[int] | None:
        catalogue = self.provider_names()
        if catalogue is None:
            return None
        by_name = {name.lower(): pid for pid, name in catalogue.items()}
        ids = set()
        for n in names:
            if n.lower() not in by_name:
                raise ConfigError(
                    f"unknown provider '{n}' for locale {self.clients.justwatch.locale}; "
                    "see `excludarr providers list`"
                )
            ids.add(by_name[n.lower()])
        return ids

    def provider_names(self) -> dict[int, str] | None:
        key = "provider_names_by_id"
        if key not in self._memo:
            providers = (
                self._once("provider catalogue", self._providers)
                if self.refresh
                else self._providers()
            )
            self._memo[key] = None if providers is None else {p.id: p.clear_name for p in providers}
        return self._memo[key]

    # --- streaming -------------------------------------------------------
    def _match(self, item: MediaItem, kind: Literal["MOVIE", "SHOW"]) -> str | None:
        ident = item.tmdb_id or item.imdb_id
        if not ident:
            log.debug("JustWatch match for %r: missing TMDB and IMDb IDs", item.title)
            return None
        jw = self.clients.justwatch
        key = f"jw:match:v2:{jw.locale}:{kind}:{ident}"

        def fetch():
            node_id = ""
            locales = (jw.locale, "en_US") if jw.locale != "en_US" else ("en_US",)
            for locale in locales:
                results = jw.search(item.base_title, kind, locale=locale)
                log.debug(
                    "JustWatch search for %r in %s (TMDB=%s IMDb=%s): %r",
                    item.base_title,
                    locale,
                    item.tmdb_id,
                    item.imdb_id,
                    results,
                )
                for r in results:
                    if (item.tmdb_id and r.tmdb_id == item.tmdb_id) or (
                        item.imdb_id and r.imdb_id == item.imdb_id
                    ):
                        node_id = r.node_id
                        break
                if node_id:
                    break
            return node_id

        node_id = self._cached(key, fetch, WEEK, legacy_key=f"jw:match:{kind}:{ident}")
        log.debug("JustWatch match for %r: %s", item.title, node_id or "no matching ID")
        return node_id or None

    def _offers(self, node_id: str, kind: Literal["MOVIE", "SHOW"]) -> dict[tuple[int, int], Avail]:
        """Offers per (season, episode); a movie is stored under (0, 0)."""
        key = f"jw:offers:v2:{node_id}"

        def fetch():
            jw = self.clients.justwatch
            if kind == "MOVIE":
                offers = {(0, 0): jw.movie_offers(node_id)}
            else:
                offers = jw.show_offers(node_id)
            return [
                [s, e, sorted(a, key=lambda offer: (offer[0], offer[1], offer[2] or ""))]
                for (s, e), a in offers.items()
            ]

        cached = self._cached(key, fetch, DAY)
        return {(s, e): frozenset((p, m, q) for p, m, q in a) for s, e, a in cached}

    def streaming(self, item: MediaItem) -> list[Avail] | None:
        """One Avail per atomic unit; [] means "no aired units", None means unknown."""
        memo_key = ("streaming", item.key)
        if memo_key not in self._memo:
            if "justwatch" in self._failed:
                log.debug("JustWatch offers for %r: skipped after service failure", item.title)
                return None
            result = self._streaming(item)
            self._memo[memo_key] = result
            if log.isEnabledFor(logging.DEBUG):
                if result is None:
                    log.debug("JustWatch offers for %r: unknown", item.title)
                else:
                    log.debug(
                        "JustWatch offers for %r: %d units, provider IDs and offer types %s",
                        item.title,
                        len(result),
                        sorted(
                            {offer for unit in result for offer in unit},
                            key=lambda offer: (offer[0], offer[1], offer[2] or ""),
                        ),
                    )
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
                    log.warning("JustWatch unavailable, further streaming lookups skipped: %s", e)
                return None
            log.warning("JustWatch lookup failed for %s: %s", item.title, e)
            return None
        except Exception as e:  # noqa: BLE001 - one bad title must never abort a run
            log.warning("JustWatch lookup failed for %s: %s", item.title, e)
            return None
        if item.kind == "movie":
            return [offers.get((0, 0), frozenset())]
        if isinstance(item, ListItem):
            units = [key for key in offers if key[0] >= 1]
            return [offers[key] for key in units] if units else None
        if item.kind == "episode":
            units = [(item.season, item.episode)]
        else:
            units = [
                (e.season, e.number)
                for e in item.episodes
                if e.aired and (e.season == item.season if item.kind == "season" else e.season >= 1)
            ]
        return [offers.get(u, frozenset()) for u in units]

    def prefetch_streaming(
        self,
        items: list[MediaItem],
        progress: Callable[[str, int, int | None], None] = lambda message, done, total: None,
    ) -> None:
        distinct = {(i.kind == "movie", i.tmdb_id, i.imdb_id): i for i in items}
        progress("Checking JustWatch availability", 0, len(distinct))
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(self.streaming, item) for item in distinct.values()]
            for done, future in enumerate(as_completed(futures), 1):
                future.result()
                progress("Checking JustWatch availability", done, len(distinct))

    def streaming_labels(self, item: MediaItem) -> list[str] | None:
        """Configured providers and offer types, with aired episode coverage."""
        configured = {name.casefold() for name in self.config.profile.providers}
        if not configured:
            return []
        if not self.clients.justwatch:
            return ["Not configured"]
        units = self.streaming(item)
        if units is None:
            return None
        if not any(units):
            return []
        providers = self._once("provider_names", self._providers)
        if providers is None:
            return None
        names = {p.id: p.clear_name for p in providers if p.clear_name.casefold() in configured}
        counts: dict[tuple[int, str], int] = {}
        for offers in units:
            for offer in {(pid, kind) for pid, kind, quality in offers}:
                if offer[0] in names:
                    counts[offer] = counts.get(offer, 0) + 1
        labels = []
        for (provider, kind), count in counts.items():
            label = names[provider]
            if kind != "FLATRATE":
                label += f" ({kind.lower()})"
            if count < len(units):
                label += f" · {count}/{len(units)} episodes"
            labels.append(label)
        return sorted(labels, key=str.casefold)

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

    def _scan_plex(self, plex: PlexClient) -> dict[tuple[str, str], PlexItem]:
        result = plex.items_by_guid()
        try:
            self.repo.rating_keys_record({k: v.rating_key for k, v in result.items()})
        except Exception as e:  # noqa: BLE001 - live Plex data stays correct without storage
            log.warning("Could not store Plex rating keys: %s", e)
        return result

    def plex_library(self) -> dict[tuple[str, str], PlexItem] | None:
        if not (plex := self.clients.plex):
            return None
        return self._once("plex", lambda: self._scan_plex(plex))

    @staticmethod
    def _external_ids(item: MediaItem) -> tuple[str, list[str]]:
        kind = "movie" if item.kind == "movie" else "show"
        ids = (
            ("tmdb", item.tmdb_id),
            ("imdb", item.imdb_id),
            ("tvdb", item.tvdb_id),
        )
        return kind, [f"{prefix}://{ident}" for prefix, ident in ids if ident]

    def plex_item(self, item: MediaItem) -> PlexItem | None:
        by_guid = self.plex_library()
        if by_guid is None:
            return None
        kind, ids = self._external_ids(item)
        for external_id in ids:
            if (kind, external_id) in by_guid:
                return by_guid[(kind, external_id)]
        return None

    def rating_keys(self, item: MediaItem) -> set[str]:
        """The live Plex key plus every key stored for the item's external ids."""
        kind, ids = self._external_ids(item)
        memo_key = ("rating_keys", kind, *ids)
        if memo_key not in self._memo:
            live = self.plex_item(item)  # scan first: it records keys and drops rematched rows
            keys = self.repo.rating_keys_for(kind, ids)
            if live:
                keys.add(live.rating_key)
            self._memo[memo_key] = keys
        return self._memo[memo_key]

    def movie_viewer_labels(self, item: MediaItem) -> list[str] | None:
        if not (self.clients.plex and self.clients.tautulli):
            return ["Not configured"]
        watched = self.watch(item)
        if watched is not None:
            return watched.watched_users
        if "plex" not in self._failed and not self.rating_keys(item):
            return ["Not in Plex"]
        return None

    def watch(self, item: MediaItem) -> WatchStats | None:
        if not (self.clients.tautulli and self.clients.plex):
            log.debug("Watch history for %r: Plex or Tautulli not configured", item.title)
            return None
        units = {
            (e.season, e.number)
            for e in item.episodes
            if e.aired and (e.season >= 1 if item.kind == "series" else e.season == item.season)
        }
        if item.kind != "movie" and not units:
            return None  # nothing aired: nothing to watch, so watch facts are unknown
        keys = self.rating_keys(item)
        history = self._once("tautulli", self.clients.tautulli.history)
        if not keys:
            reason = "Plex lookup failed" if "plex" in self._failed else "no known rating key"
            log.debug("Watch history for %r: %s", item.title, reason)
            return None
        if history is None:
            log.debug("Watch history for %r: Tautulli history unavailable", item.title)
            return None
        if item.kind == "movie":
            rows = [r for r in history if r.rating_key in keys]
        else:
            rows = [
                r
                for r in history
                if r.grandparent_rating_key in keys
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
        users = {}
        for r in sorted(watched, key=lambda row: row.at):
            name = r.friendly_name or r.user or "Unknown viewer"
            users[(r.user or name).casefold()] = name
        return WatchStats(
            last_watched=max((r.at for r in rows), default=None),
            play_count=len(watched),
            fully_watched=full,
            last_by_user=last_by_user,
            watched_users=sorted(set(users.values()), key=str.casefold),
        )

    def requester_labels(self, item: MediaItem) -> list[str] | None:
        if not self.clients.seerr:
            return ["Not configured"]
        requests = self.requests(item)
        if requests is None:
            return None
        names = {
            request.requester_name or next(iter(sorted(request.requested_by)), "Unknown requester")
            for request in requests
        }
        return sorted(names, key=str.casefold)

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
