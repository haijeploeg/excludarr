"""Resolve external IDs and requested metadata without title-only matching."""

from dataclasses import replace

from excludarr.clients.http import HttpClient
from excludarr.clients.list_sources import ListDataError, defensive, imdb_id, numeric_id
from excludarr.lists.items import ListItem


class TmdbClient:
    def __init__(self, token: str, http: HttpClient | None = None):
        self.http = http or HttpClient(
            "tmdb", "https://api.themoviedb.org", {"Authorization": "Bearer " + token}
        )

    @defensive
    def enrich(self, item: ListItem, fields: frozenset[str]) -> ListItem:
        media = "movie" if item.kind == "movie" else "tv"
        ident = item.tmdb_id
        if ident is None:
            external = item.imdb_id or item.tvdb_id
            source = "imdb_id" if item.imdb_id else "tvdb_id"
            if external is None:
                raise ListDataError("no identity")
            data = self.http.get(f"/3/find/{external}", params={"external_source": source})
            matches = data[f"{media}_results"]
            if not isinstance(matches, list) or len(matches) != 1:
                raise ListDataError("external ID not uniquely resolved")
            ident = numeric_id(matches[0]["id"])
        if ident is None:
            raise ListDataError("missing TMDB ID")
        data = self.http.get(f"/3/{media}/{ident}", params={"append_to_response": "external_ids"})
        if numeric_id(data["id"]) != ident:
            raise ListDataError("conflicting TMDB ID")
        external = data["external_ids"]
        imdb = imdb_id(external.get("imdb_id"))
        tvdb = numeric_id(external.get("tvdb_id"))
        if (
            item.imdb_id
            and imdb
            and item.imdb_id != imdb
            or item.tvdb_id
            and tvdb
            and item.tvdb_id != tvdb
        ):
            raise ListDataError("conflicting external ID")
        result = replace(
            item, tmdb_id=ident, imdb_id=item.imdb_id or imdb, tvdb_id=item.tvdb_id or tvdb
        )
        if "year" in fields:
            date = data.get("release_date" if media == "movie" else "first_air_date")
            result.year = int(date[:4]) if date else None
        if "genres" in fields:
            genres = data.get("genres")
            if genres is not None:
                if not isinstance(genres, list) or not all(
                    isinstance(g.get("name"), str) for g in genres
                ):
                    raise ListDataError("invalid genres")
                result.genres = frozenset(g["name"] for g in genres)
        if "ratings" in fields:
            rating = data.get("vote_average")
            if rating is not None:
                if type(rating) not in (int, float) or not 0 <= rating <= 10:
                    raise ListDataError("invalid rating")
                result.ratings = {"tmdb": rating}
        if "ended" in fields:
            status = data.get("status")
            result.ended = None if not status else status in ("Ended", "Canceled")
        return result
