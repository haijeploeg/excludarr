"""Read-only source lists. Upstream response shapes are validated before publication."""

import functools
import re
import time
from urllib.parse import quote

from excludarr.clients.http import HttpClient, IntegrationError
from excludarr.list_config import SourceConfig
from excludarr.lists.items import ListItem


class ListDataError(ValueError):
    """A validation failure whose message contains no upstream values or credentials."""


def defensive(fn):
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (KeyError, TypeError, AttributeError, ValueError, IndexError) as error:
            if isinstance(error, ListDataError):
                reason = str(error)
            elif isinstance(error, KeyError):
                reason = f"missing response field {error.args[0]!r}"
            else:
                reason = f"unexpected response shape ({type(error).__name__})"
            raise IntegrationError("lists", reason) from error

    return wrapped


def numeric_id(value):
    if value is None or value == 0 and not isinstance(value, bool):
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ListDataError("invalid numeric ID")
    return value


def imdb_id(value):
    if value in (None, ""):
        return None
    if not isinstance(value, str) or not re.fullmatch(r"tt[0-9]+", value):
        raise ListDataError("invalid IMDb ID")
    return value


def _item(title, kind, *, year=None, tmdb=None, imdb=None, tvdb=None):
    if not isinstance(title, str) or not title.strip():
        raise ListDataError("missing title")
    if year is not None and (type(year) is not int or year < 1):
        raise ListDataError("invalid year")
    item = ListItem(title, kind, year, numeric_id(tmdb), imdb_id(imdb), numeric_id(tvdb))
    if not (item.tmdb_id or item.imdb_id or item.tvdb_id):
        raise ListDataError("missing identity")
    return item


def _array(value):
    if not isinstance(value, list):
        raise ListDataError("expected array")
    return value


def _trakt_item(raw, mode, media):
    kind = media
    if mode != "popular":
        typ = raw.get("type")
        if typ in ("season", "episode", "person"):
            return None
        kind = "movie" if "movie" in raw else "series" if "show" in raw else None
        if kind is None:
            raise ListDataError("invalid Trakt item")
        raw = raw["movie" if kind == "movie" else "show"]
    ids = raw["ids"]
    return _item(
        raw["title"],
        kind,
        year=raw.get("year"),
        tmdb=ids.get("tmdb"),
        imdb=ids.get("imdb"),
        tvdb=ids.get("tvdb"),
    )


@defensive
def fetch_source(source: SourceConfig, *, tmdb_token: str | None) -> list[ListItem]:
    typ = source.type
    token = source.token.get_secret_value() if source.token else tmdb_token
    headers = {"Accept": "application/json"}
    if typ == "stevenlu":
        http = HttpClient("stevenlu", source.url, headers)
        try:
            return [
                _item(r["title"], "movie", imdb=r["imdb_id"]) for r in _array(http.get(source.url))
            ]
        finally:
            http._client.close()
    if typ == "trakt":
        base = "https://api.trakt.tv"
        headers |= {"trakt-api-version": "2", "trakt-api-key": source.client_id.get_secret_value()}
        if source.token:
            headers["Authorization"] = "Bearer " + token
        if source.mode == "list":
            path = f"/users/{quote(source.user, safe='')}/lists/{quote(str(source.list_id), safe='')}/items"
        elif source.mode == "watchlist":
            path = "/sync/watchlist"
        else:
            path = f"/{'movies' if source.media_type == 'movie' else 'shows'}/{source.mode}"
    elif typ == "tmdb":
        if not token:
            raise IntegrationError("tmdb", "read token required")
        base = "https://api.themoviedb.org"
        headers["Authorization"] = "Bearer " + token
        media = "movie" if source.media_type == "movie" else "tv"
        path = (
            f"/4/list/{source.list_id}"
            if source.mode == "list"
            else (
                f"/3/{media}/popular"
                if source.mode == "popular"
                else f"/3/trending/{media}/{source.time_window}"
            )
        )
    else:
        base = "https://discover.provider.plex.tv"
        headers["X-Plex-Token"] = token
        path = "/library/sections/watchlist/all"
    http = HttpClient(typ, base, headers)
    result = []
    seen = set()
    page, offset = 1, 0
    chart = source.mode in ("popular", "trending")
    try:
        while True:
            params = {"page": page, "limit": 100} if typ == "trakt" else {"page": page}
            if typ == "plex_watchlist":
                params = {
                    "includeGuids": 1,
                    "X-Plex-Container-Start": offset,
                    "X-Plex-Container-Size": 100,
                    "sort": "watchlistedAt:desc",
                }
            try:
                data = http.get(path, params=params)
            except IntegrationError as error:
                raise IntegrationError(typ, f"page {page}: {error}", error.status) from error
            if typ == "trakt":
                rows = _array(data)
                more = len(rows) == 100
            elif typ == "tmdb":
                rows = _array(data["results"])
                if type(data["page"]) is not int or data["page"] != page:
                    raise ListDataError("unexpected page")
                total = data["total_pages"]
                if type(total) is not int or total < 0:
                    raise ListDataError("invalid page count")
                more = page < total
            else:
                container = data["MediaContainer"]
                rows = _array(container.get("Metadata", []))
                total = container["totalSize"]
                if type(total) is not int or total < 0:
                    raise ListDataError("invalid size")
                more = offset + len(rows) < total
            signature = repr(rows)
            if more and not rows or rows and signature in seen:
                raise ListDataError("pagination did not advance")
            seen.add(signature)
            for raw in rows:
                if typ == "trakt":
                    item = _trakt_item(raw, source.mode, source.media_type)
                elif typ == "tmdb":
                    media = raw.get(
                        "media_type",
                        "movie"
                        if source.media_type == "movie"
                        else "tv"
                        if source.media_type
                        else None,
                    )
                    if media not in ("movie", "tv"):
                        raise ListDataError("invalid media type")
                    item = _item(
                        raw["title" if media == "movie" else "name"],
                        "movie" if media == "movie" else "series",
                        tmdb=raw["id"],
                    )
                else:
                    media = raw["type"]
                    if media not in ("movie", "show"):
                        raise ListDataError("invalid Plex type")
                    ids = {}
                    for guid in raw.get("Guid", []):
                        value = guid["id"]
                        scheme, sep, ident = value.partition("://")
                        if sep and scheme in ("imdb", "tmdb", "tvdb"):
                            converted = ident if scheme == "imdb" else int(ident)
                            if scheme in ids and ids[scheme] != converted:
                                raise ListDataError("conflicting Plex GUID")
                            ids[scheme] = converted
                    item = _item(
                        raw["title"],
                        "movie" if media == "movie" else "series",
                        year=raw.get("year"),
                        **ids,
                    )
                if item is not None:
                    result.append(item)
                if chart and len(result) >= source.limit:
                    return result[: source.limit]
            if not more:
                return result
            page += 1
            offset += len(rows)
            if typ == "plex_watchlist":
                time.sleep(5)  # Plex discovery pacing, matching arr's request interval.
    finally:
        http._client.close()
