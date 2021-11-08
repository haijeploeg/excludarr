#!/usr/bin/env python

from ..base import Manager


class Serie(Manager):
    def __init__(self, client):
        super().__init__(client)
        self.serie_path = "/series"
        self.serie_id_path = "/series/{id}".format(id="{id}")

    def get_all_series(self):
        return self.client.http_get(self.serie_path)
