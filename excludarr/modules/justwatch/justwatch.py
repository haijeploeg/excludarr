from typing import Any, Dict, List, TypeAlias
import re
import httpx
from loguru import logger

from json import JSONDecodeError

from .exceptions import (
    JustWatchBadJSON,
    JustWatchGraphqlError,
    JustWatchTooManyRequests,
    JustWatchForbidden,
    JustWatchNotFound,
    JustWatchBadRequest,
)
from .models import MovieOffers, SearchResult, Offer, ShowOffers

JSON: TypeAlias = (
    dict[str, "JSON"] | list["JSON"] | str | int | float | bool | None
)


class JustWatch(object):
    httpx_client: httpx.Client
    _locale: str
    _language: str
    _country: str

    graphql_url: str = "https://apis.justwatch.com/graphql"

    def __init__(self, locale, ssl_verify: bool = True):
        # TODO: understand how to write this retry strategy with httpx
        # # Setup retries on failure
        # retries = Retry(
        #     total=5,
        #     backoff_factor=0.5,
        #     status_forcelist=[429, 500, 502, 503, 504],
        #     allowed_methods=["GET", "POST"],
        # )

        self.httpx_client = httpx.Client(http2=True, verify=ssl_verify)

        # Setup locale by verifying its input
        self._locale = self._get_full_locale(locale)
        [self._language, self._country] = self._locale.split("_")

    def __exit__(self, *args):
        self.httpx_client.close()

    def _filter_api_error(self, data: httpx.Response):

        if data.status_code == 400:
            raise JustWatchBadRequest(data.text)
        if data.status_code == 403:
            raise JustWatchForbidden()
        if data.status_code == 403:
            raise JustWatchForbidden()
        elif data.status_code == 404:
            raise JustWatchNotFound()
        elif data.status_code == 429:
            raise JustWatchTooManyRequests()

        try:
            j = data.json()
        except JSONDecodeError:
            raise JustWatchBadJSON(data.text)

        # TODO: write custom retry strategy based on graphql errors
        #       we can't base out retry strategy on response codes because the
        #       rpc always returns 200 if it is available, for now this will do
        if "errors" in j:
            raise JustWatchGraphqlError(data)

        return j

    def _graphql_post(self, request: Dict[str, Any]):
        # JustWatch returns a 403 without a reasonable User-Agent
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36"  # noqa: E501
        }
        response = self.httpx_client.post(
            self.graphql_url, headers=headers, json=request
        )

        return self._filter_api_error(response)

    def _get_full_locale(self, locale: str):
        if re.fullmatch(r"[a-z]{2}_[A-Z]{2}", locale):
            return locale
        if re.fullmatch(r"[A-Za-z]{2}", locale):
            return f"en_{locale.upper()}"
        return "en_US"

    def get_providers(self):
        result = self._graphql_post(
            {
                "operationName": "GetPackages",
                "query": (
                    "query GetPackages($country: Country!, "
                    "$platform: Platform!) { "
                    "packages(country: $country, platform: $platform) { "
                    "packageId clearName technicalName shortName "
                    "monetizationTypes } }"
                ),
                "variables": {"country": self._country, "platform": "WEB"},
            }
        )
        return [
            {
                "id": package["packageId"],
                "clear_name": package["clearName"],
                "technical_name": package["technicalName"],
                "short_name": package["shortName"],
                "monetization_types": [
                    value.lower() for value in package["monetizationTypes"]
                ],
            }
            for package in result["data"]["packages"]
        ]

    def query_movie_offers(
        self, jwid: str, providers: List[str] = [], forceFlatrate=False
    ) -> MovieOffers | None:

        try:
            result_json = self._get_providers(jwid, providers, forceFlatrate)
        except Exception:
            logger.exception("Failed to query JustWatch movie offers")
            return None

        result: MovieOffers = []

        for offer in result_json["data"]["node"]["offers"]:
            result.append(Offer(offer))

        return result

    def query_show_offers(
        self, jwid: str, providers: List[str] = [], forceFlatrate=False
    ) -> ShowOffers | None:

        try:
            result_json = self._get_providers(jwid, providers, forceFlatrate)
        except Exception:
            logger.exception("Failed to query JustWatch show offers")
            return None

        result: ShowOffers = {}

        for season in result_json["data"]["node"]["seasons"]:
            season_n = season["content"]["seasonNumber"]
            result[season_n] = {}

            for episode in season["episodes"]:
                episode_n = episode["content"]["episodeNumber"]
                result[season_n][episode_n] = []

                for offer in episode["offers"]:
                    result[season_n][episode_n].append(Offer(offer))

        return result

    def search_movie(
        self, title: str, results=4, year: int | None = None
    ) -> list[SearchResult] | None:
        try:
            return self._search(title, "MOVIE", results, year)
        except Exception:
            logger.exception("Failed to search JustWatch movies")
            return None

    def search_show(
        self, title: str, results=4, year: int | None = None
    ) -> list[SearchResult] | None:

        try:
            return self._search(title, "SHOW", results, year)
        except Exception:
            logger.exception("Failed to search JustWatch shows")
            return None

    def _search(
        self, title, objectType: str, results: int = 1, year: int | None = None
    ) -> list[SearchResult]:

        from .queries import SEARCH_QUERY as query

        filter = {}

        filter["searchQuery"] = title
        filter["objectTypes"] = [objectType]
        if year is not None:
            filter["releaseYear"] = {
                "min": year,
                "max": year,
            }

        request = {
            "operationName": "GetSearchTitles",
            "query": query,
            "variables": {
                "first": results,
                "searchTitlesFilter": filter,
                "language": self._language,
                "country": self._country,
            },
        }

        filtered = self._graphql_post(request)

        ret = []
        for node in filtered["data"]["popularTitles"]["edges"]:
            ret.append(SearchResult(node["node"]))

        return ret

    def _get_providers(
        self, jwid: str, providers: List[str] = [], forceFlatrate: bool = False
    ):

        from .queries import OFFER_QUERY as query

        # MONETIZATION_TYPES = ["FLATRATE", "RENT", "BUY", "ADS", "FREE"]
        # PRESENTATION_TYPES = ["SD", "HD", "_4K"]

        # TODO: check if there is a way to bypass language checks because atm
        #       ie. you set "en_IT" you will only find movies that are
        #       distributed in italy in english.
        #       if we find a way to bypass this we could apply some kind of
        #       multi language filter based on the config
        filter: Dict[str, Any] = {}

        filter["bestOnly"] = True

        if forceFlatrate:
            filter["monetizationTypes"] = ["FLATRATE"]
        if len(providers) > 0:
            filter["packages"] = providers

        request: Any = {
            "operationName": "GetTitleOffers",
            "query": query,
            "variables": {
                "nodeId": jwid,
                "language": self._language,
                "country": self._country,
                "offerFilter": filter,
            },
        }

        return self._graphql_post(request)
