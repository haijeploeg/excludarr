"""Validated configuration for external source and outgoing lists."""

from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, PlainValidator, SecretStr, model_validator

from excludarr.conditions import Condition, leaves, parse_condition
from excludarr.scheduling import Schedule

ParsedCondition = Annotated[Condition, PlainValidator(parse_condition)]
Secret = Annotated[SecretStr, Field(min_length=1)]
Slug = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")]


class SourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["trakt", "stevenlu", "plex_watchlist", "tmdb"]
    mode: Literal["popular", "trending", "list", "watchlist"] | None = None
    media_type: Literal["movie", "series"] | None = None
    limit: Annotated[int, Field(strict=True, ge=1, le=1000)] = 100
    time_window: Literal["day", "week"] = "week"
    user: str | None = None
    list_id: str | Annotated[int, Field(strict=True, gt=0)] | None = None
    client_id: Secret | None = None
    token: Secret | None = None
    url: str = "https://s3.amazonaws.com/popular-movies/movies.json"

    @model_validator(mode="after")
    def _validate_mode(self):
        used = self.model_fields_set - {"type"}
        allowed = set()
        if self.type in ("trakt", "tmdb"):
            if self.mode is None:
                raise ValueError("trakt/tmdb source requires mode")
            allowed = {"mode", "token"}
            if self.type == "trakt":
                allowed.add("client_id")
                if self.client_id is None:
                    raise ValueError("trakt source requires client_id")
            if self.mode in ("popular", "trending"):
                allowed |= {"media_type", "limit"}
                if self.media_type is None:
                    raise ValueError("chart requires media_type")
                if self.type == "tmdb" and self.mode == "trending":
                    allowed.add("time_window")
            elif self.mode == "list":
                allowed.add("list_id")
                if not self.list_id or isinstance(self.list_id, bool):
                    raise ValueError("saved list requires list_id")
                if self.type == "tmdb" and (not isinstance(self.list_id, int)):
                    raise ValueError("TMDB list_id must be a positive integer")
                if self.type == "trakt":
                    allowed.add("user")
                    if not self.user:
                        raise ValueError("Trakt saved list requires user")
            elif self.type != "trakt" or self.token is None:
                raise ValueError("watchlist mode requires Trakt access token")
        elif self.type == "plex_watchlist":
            allowed = {"token"}
            if self.token is None:
                raise ValueError("Plex Watchlist requires token")
        else:
            allowed = {"url"}
            parts = urlsplit(self.url)
            if (
                parts.scheme not in ("http", "https")
                or not parts.hostname
                or parts.username
                or parts.password
                or parts.query
                or parts.fragment
            ):
                raise ValueError(
                    "source URL must be HTTP(S), without credentials, query or fragment"
                )
        if used - allowed:
            raise ValueError(
                "fields not applicable to source mode: " + ", ".join(sorted(used - allowed))
            )
        return self


class ProxyList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: Literal["radarr", "sonarr"]
    sources: Annotated[list[Slug], Field(min_length=1)]
    when: ParsedCondition
    unless: list[ParsedCondition] = []
    on_unknown: Literal["include", "exclude"] = "include"
    schedule: Schedule = None

    @model_validator(mode="after")
    def _conditions(self):
        for c in [self.when, *self.unless]:
            for leaf in leaves(c):
                if leaf.name not in {"year", "genre", "rating", "status", "streaming"}:
                    raise ValueError("condition is not available for list items: " + leaf.name)
                if leaf.name == "status" and self.target != "sonarr":
                    raise ValueError("status requires sonarr target")
                if leaf.name == "rating" and leaf.params[0] != "tmdb":
                    raise ValueError("list rating source must be tmdb")
        return self


class ListProxyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: Secret
    tmdb_token: Secret | None = None
    sources: dict[Slug, SourceConfig]
    lists: dict[Slug, ProxyList]

    @model_validator(mode="after")
    def _references(self):
        for rule in self.lists.values():
            for name in rule.sources:
                if name not in self.sources:
                    raise ValueError("unknown list source: " + name)
                source = self.sources[name]
                kind = "movie" if rule.target == "radarr" else "series"
                if (
                    source.type == "stevenlu"
                    and kind != "movie"
                    or source.media_type
                    and source.media_type != kind
                ):
                    raise ValueError("source media type does not match list target")
                if source.type == "tmdb" and not (source.token or self.tmdb_token):
                    raise ValueError("TMDB source requires token or list_proxy.tmdb_token")
        return self
