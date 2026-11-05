"""Seerr (Overseerr/Jellyseerr) client: requests and cleanup."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from excludarr.clients.http import HttpClient
from excludarr.config import Integration

TAKE = 100


@dataclass
class SeerrRequest:
    id: int
    media_id: int
    media_type: Literal["movie", "tv"]
    tmdb_id: int | None
    tvdb_id: int | None
    created_at: datetime
    requested_by: frozenset[str]
    seasons: frozenset[int]


def _parse(r: dict) -> SeerrRequest:
    media = r["media"]
    by = r.get("requestedBy") or {}
    created = datetime.fromisoformat(r["createdAt"])
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return SeerrRequest(
        id=r["id"],
        media_id=media["id"],
        media_type=r.get("type") or media["mediaType"],
        tmdb_id=media.get("tmdbId"),
        tvdb_id=media.get("tvdbId"),
        created_at=created.astimezone(UTC),
        requested_by=frozenset(
            by[k].lower() for k in ("plexUsername", "displayName", "email") if by.get(k)
        ),
        seasons=frozenset(s["seasonNumber"] for s in r.get("seasons") or []),
    )


class SeerrClient:
    def __init__(self, cfg: Integration, http: HttpClient | None = None):
        self.http = http or HttpClient(
            "seerr", f"{cfg.url}/api/v1", {"X-Api-Key": cfg.api_key}, verify=cfg.verify_ssl
        )

    def requests(self) -> list[SeerrRequest]:
        out: list[SeerrRequest] = []
        skip, page = 0, 0
        while True:
            page += 1
            data = self.http.get("/request", params={"take": TAKE, "skip": skip, "filter": "all"})
            out += [_parse(r) for r in data["results"]]
            pages = data["pageInfo"]["pages"]
            skip += len(data["results"])
            if not data["results"] or page >= pages:
                return out

    def delete_media(self, media_id: int) -> None:
        self.http.delete(f"/media/{media_id}")

    def delete_request(self, request_id: int) -> None:
        self.http.delete(f"/request/{request_id}")
