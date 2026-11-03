from typing import Any, Dict, List, TypeAlias
import httpx

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

    base_url: str = "https://apis.justwatch.com/content"
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

    def _build_url(self, path: str):
        return "{}{}".format(self.base_url, path)

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

    def _http_request(
        self,
        method: str,
        path: str,
        json: Any | None = None,
        params: httpx.QueryParams | None = None,
    ):
        # JustWatch returns a 403 without a reasonable User-Agent
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36"  # noqa: E501
        }
        url = self._build_url(path)

        request = self.httpx_client.build_request(
            method, url, headers=headers, json=json, params=params
        )

        result = self.httpx_client.send(request)

        return self._filter_api_error(result)

    def _http_get(self, path: str, params: httpx.QueryParams | None = None):
        return self._http_request("get", path, params=params)

    def _http_post(self, path: str, json: Any | None = None):
        return self._http_request("post", path, json=json)

    def _http_put(
        self,
        path: str,
        json: Any | None = None,
        params: httpx.QueryParams | None = None,
    ):
        return self._http_request("put", path, params=params, json=json)

    def _http_delete(
        self,
        path: str,
        json: Any | None = None,
        params: httpx.QueryParams | None = None,
    ):
        return self._http_request("delete", path, json=json, params=params)

    def _get_full_locale(self, locale: str):
        default_locale = "en_US"
        path = "/locales/state"

        jw_locales = self._http_get(path)

        valid_locale = any(
            [True for i in jw_locales if i["full_locale"] == locale]
        )

        # Check if the locale is a iso_3166_2 Country Code
        if not valid_locale:
            locale = "".join(
                [
                    i["full_locale"]
                    for i in jw_locales
                    if i["iso_3166_2"] == locale
                ]
            )

        # If the locale is empty return the default locale
        if not locale:
            return default_locale

        return locale

    def get_providers(self):
        path = f"/providers/locale/{self._locale}"

        return self._http_get(path)

    def query_movie_offers(
        self, jwid: str, providers: List[str] = [], forceFlatrate=False
    ) -> MovieOffers | None:

        try:
            result_json = self._get_providers(jwid, providers, forceFlatrate)
        except Exception:
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
            return None

    def search_show(
        self, title: str, results=4, year: int | None = None
    ) -> list[SearchResult] | None:

        try:
            return self._search(title, "SHOW", results, year)
        except Exception:
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

        response = self.httpx_client.post(self.graphql_url, json=request)

        filtered = self._filter_api_error(response)

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

        response = self.httpx_client.post(self.graphql_url, json=request)

        return self._filter_api_error(response)
