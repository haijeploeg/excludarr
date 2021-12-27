#!/usr/bin/env python

import requests

from .exceptions import (
    RadarrInvalidIdSupplied,
    RadarrInvalidApiKey,
    RadarrMovieNotFound,
    RadarrValidationException,
)
from .v3.movie import Movie
from .v3.moviefile import MovieFile


class Radarr(object):
    def __init__(self, base_url, api_key, ssl_verify=True):
        # Setup base variables
        self._base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_url = "{}/api/v3".format(self._base_url)

        # Setup session
        self.session = requests.Session()
        self.session.verify = ssl_verify
        self.session.headers.update({"X-Api-Key": self.api_key})

        # Register managers based on api version
        self.movie = Movie(self)
        self.moviefile = MovieFile(self)

    def __exit__(self, *args):
        self.session.close()

    def _build_url(self, path):
        return "{}{}".format(self.api_url, path)

    def _filter_api_error(self, data):
        if data.status_code == 400:
            raise RadarrInvalidIdSupplied(
                "Invalid ID supplied! The error message is: {}".format(data.text)
            )
        elif data.status_code == 401:
            raise RadarrInvalidApiKey("Invalid API key")
        elif data.status_code == 404:
            raise RadarrMovieNotFound("Movie not found")
        elif data.status_code == 405:
            raise RadarrValidationException("Validation exception")

        result_json = data.json()

        return result_json

    def http_request(self, method, path, json=None, params=None, retries=3):
        url = self._build_url(path)
        request = requests.Request(method, url, json=json, params=params)

        prepped = self.session.prepare_request(request)
        result = self.session.send(prepped)

        try:
            return self._filter_api_error(result)
        except ValueError:
            if retries != 0:
                retries -= 1
                self.http_request(method, path, json, params, retries)
            else:
                raise

    def http_get(self, path, params=None):
        return self.http_request("get", path, params=params)

    def http_post(self, path, json=None):
        return self.http_request("post", path, json=json)

    def http_put(self, path, params=None, json=None):
        return self.http_request("put", path, params=params, json=json)

    def http_delete(self, path, json=None, params=None):
        return self.http_request("delete", path, json=json, params=params)
