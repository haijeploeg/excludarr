#!/usr/bin/env python

from ..base import Manager


class EpisodeFile(Manager):
    def __init__(self, client):
        super().__init__(client)
        self.episodefile_path = "/episodefile"
        self.episodefile_id_path = "/episodefile/{id}".format(id="{id}")

    def get_episodefiles(self, series_id):
        params = {
            "seriesId": series_id,
        }
        return self.client.http_get(self.episodefile_path, params=params)

    def get_episodefile(self, id):
        return self.client.http_get(self.episodefile_id_path.format(id=id))

    def delete_episodefile(self, id):
        return self.client.http_delete(self.episodefile_id_path.format(id=id))
