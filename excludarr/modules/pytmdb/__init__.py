#!/usr/bin/env python

# Imports
import requests

from json import JSONDecodeError

from .exceptions import TMDBException
from .v3.movies import Movie
from .v3.tv import TV
from .v3.find import Find


class TMDB(object):
    def __init__(self, api_key, api_version="3", ssl_verify=True):
        # Setup base variables
        self._api_version = str(api_version)
        self._base_url = "https://api.themoviedb.org"
        self.api_url = "{}/{}".format(self._base_url, self._api_version)
        self.api_key = api_key

        # Setup session
        self.session = requests.Session()
        self.session.verify = ssl_verify
        self.session.params = {"api_key": self.api_key}

        # Register managers
        self.movie = Movie(self)
        self.tv = TV(self)
        self.find = Find(self)

    def __exit__(self, *args):
        self.session.close()

    def _build_url(self, path):
        return "{}{}".format(self.api_url, path)

    def _filter_api_error(self, data):
        if not data.get("success", True):
            status_code = data.get("status_code", "")
            status_message = data.get("status_message", "")
            raise TMDBException(status_code, status_message)

        return data

    def http_request(self, method, path, json=None, params=None):
        url = self._build_url(path)
        request = requests.Request(method, url, json=json, params=params)

        prepped = self.session.prepare_request(request)
        result = self.session.send(prepped)

        try:
            result_json = result.json()
        except JSONDecodeError:
            return result.text

        return self._filter_api_error(result_json)

    def http_get(self, path, params=None):
        return self.http_request("get", path, params=params)
