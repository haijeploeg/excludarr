"""JustWatch GraphQL client."""

import functools
import re
from dataclasses import dataclass
from typing import Literal

from excludarr.clients.http import HttpClient, IntegrationError
from excludarr.clients.justwatch_queries import OFFER_QUERY, SEARCH_QUERY

# JustWatch returns 403 without a browser-like User-Agent.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36"
)
PACKAGES_QUERY = (
    "query GetPackages($country: Country!, $platform: Platform!) { "
    "packages(country: $country, platform: $platform) { "
    "packageId clearName technicalName shortName monetizationTypes } }"
)

# Set of (packageId, MONETIZATION) pairs.
Avail = frozenset[tuple[int, str]]


def normalize_locale(locale: str) -> str:
    if re.fullmatch(r"[a-z]{2}_[A-Z]{2}", locale):
        return locale
    if re.fullmatch(r"[A-Za-z]{2}", locale):
        return f"en_{locale.upper()}"
    return "en_US"


@dataclass
class Provider:
    id: int
    clear_name: str
    short_name: str
    monetization_types: list[str]


@dataclass
class SearchResult:
    node_id: str
    title: str
    year: int | None
    tmdb_id: int | None
    imdb_id: str | None


def _defensive(fn):
    """Turn malformed response shapes into IntegrationError."""

    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except (KeyError, TypeError, AttributeError, ValueError) as e:
            raise IntegrationError("justwatch", "unexpected response shape") from e

    return wrapper


def _avail(offers: list[dict]) -> Avail:
    return frozenset((o["package"]["packageId"], o["monetizationType"]) for o in offers)


class JustWatchClient:
    def __init__(self, locale: str, http: HttpClient | None = None):
        self.locale = normalize_locale(locale)
        self.language, self.country = self.locale.split("_")
        self.http = http or HttpClient(
            "justwatch", "https://apis.justwatch.com", {"User-Agent": USER_AGENT}
        )

    def _gql(self, operation: str, query: str, variables: dict) -> dict:
        res = self.http.post(
            "/graphql", json={"operationName": operation, "query": query, "variables": variables}
        )
        if not isinstance(res, dict) or "errors" in res or "data" not in res:
            raise IntegrationError("justwatch", "GraphQL error")
        return res["data"]

    @_defensive
    def providers(self) -> list[Provider]:
        data = self._gql(
            "GetPackages", PACKAGES_QUERY, {"country": self.country, "platform": "WEB"}
        )
        return [
            Provider(
                p["packageId"], p["clearName"], p["shortName"], list(p["monetizationTypes"] or [])
            )
            for p in data["packages"]
        ]

    @_defensive
    def search(
        self,
        title: str,
        kind: Literal["MOVIE", "SHOW"],
        first: int = 5,
        *,
        locale: str | None = None,
    ) -> list[SearchResult]:
        language, country = normalize_locale(locale or self.locale).split("_")
        data = self._gql(
            "GetSearchTitles",
            SEARCH_QUERY,
            {
                "first": first,
                "searchTitlesFilter": {"searchQuery": title, "objectTypes": [kind]},
                "language": language,
                "country": country,
            },
        )
        out = []
        for edge in data["popularTitles"]["edges"]:
            n = edge["node"]
            c = n["content"]
            tmdb = c["externalIds"]["tmdbId"]
            out.append(
                SearchResult(
                    n["id"],
                    c["title"],
                    c["originalReleaseYear"],
                    int(tmdb) if tmdb is not None else None,
                    c["externalIds"]["imdbId"],
                )
            )
        return out

    @_defensive
    def _offers(self, node_id: str) -> dict:
        data = self._gql(
            "GetTitleOffers",
            OFFER_QUERY,
            {
                "nodeId": node_id,
                "language": self.language,
                "country": self.country,
                "offerFilter": {"bestOnly": False},
            },
        )
        if not data.get("node"):
            raise IntegrationError("justwatch", f"no node for {node_id}")
        return data["node"]

    @_defensive
    def movie_offers(self, node_id: str) -> Avail:
        return _avail(self._offers(node_id).get("offers") or [])

    @_defensive
    def show_offers(self, node_id: str) -> dict[tuple[int, int], Avail]:
        out: dict[tuple[int, int], Avail] = {}
        for season in self._offers(node_id).get("seasons") or []:
            for ep in season["episodes"]:
                c = ep["content"]
                out[(c["seasonNumber"], c["episodeNumber"])] = _avail(ep["offers"] or [])
        return out
