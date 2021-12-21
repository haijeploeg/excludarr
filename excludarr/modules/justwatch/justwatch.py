import requests

from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from json import JSONDecodeError

from .exceptions import JustWatchTooManyRequests, JustWatchNotFound, JustWatchBadRequest


class JustWatch(object):
    def __init__(self, locale, ssl_verify=True):
        # Setup base variables
        self.base_url = "https://apis.justwatch.com/content"
        self.ssl_verify = ssl_verify

        # Setup session
        self.session = requests.Session()
        self.session.verify = ssl_verify

        # Setup retries on failure
        retries = Retry(
            total=5,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            method_whitelist=["GET", "POST"],
        )

        self.session.mount("http://", HTTPAdapter(max_retries=retries))
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

        # Setup locale by verifying its input
        self.locale = self._get_full_locale(locale)

    def __exit__(self, *args):
        self.session.close()

    def _build_url(self, path):
        return "{}{}".format(self.base_url, path)

    def _filter_api_error(self, data):

        if data.status_code == 400:
            raise JustWatchBadRequest(data.text)
        elif data.status_code == 404:
            raise JustWatchNotFound()
        elif data.status_code == 429:
            raise JustWatchTooManyRequests()

        try:
            result_json = data.json()
        except JSONDecodeError:
            return data.text

        return result_json

    def _http_request(self, method, path, json=None, params=None):
        url = self._build_url(path)
        request = requests.Request(method, url, json=json, params=params)

        prepped = self.session.prepare_request(request)
        result = self.session.send(prepped)

        return self._filter_api_error(result)

    def _http_get(self, path, params=None):
        return self._http_request("get", path, params=params)

    def _http_post(self, path, json=None):
        return self._http_request("post", path, json=json)

    def _http_put(self, path, params=None, json=None):
        return self._http_request("put", path, params=params, json=json)

    def _http_delete(self, path, json=None, params=None):
        return self._http_request("delete", path, json=json, params=params)

    def _get_full_locale(self, locale):
        default_locale = "en_US"
        path = "/locales/state"

        jw_locales = self._http_get(path)

        valid_locale = any([True for i in jw_locales if i["full_locale"] == locale])

        # Check if the locale is a iso_3166_2 Country Code
        if not valid_locale:
            locale = "".join([i["full_locale"] for i in jw_locales if i["iso_3166_2"] == locale])

        # If the locale is empty return the default locale
        if not locale:
            return default_locale

        return locale

    def get_providers(self):
        path = f"/providers/locale/{self.locale}"

        return self._http_get(path)

    def query_title(self, query, content_type, fast=True, result={}, page=1, **kwargs):
        """
        Query JustWatch API to find information about a title

        :query: the title of the show or movie to search for
        :content_type: can either be 'show' or 'movie'. Can also be a list of types.
        """
        path = f"/titles/{self.locale}/popular"

        if isinstance(content_type, str):
            content_type = content_type.split(",")

        json = {"query": query, "content_types": content_type}
        if kwargs:
            json.update(kwargs)

        page_result = self._http_post(path, json=json)
        result.update(page_result)

        if not fast and page < result["total_pages"]:
            page += 1
            self.query_title(query, content_type, fast=fast, result=result, page=page)

        return result

    def get_movie(self, jw_id):
        path = f"/titles/movie/{jw_id}/locale/{self.locale}"

        return self._http_get(path)

    def get_show(self, jw_id):
        path = f"/titles/show/{jw_id}/locale/{self.locale}"

        return self._http_get(path)

    def get_season(self, jw_id):
        path = f"/titles/show_season/{jw_id}/locale/{self.locale}"

        return self._http_get(path)
