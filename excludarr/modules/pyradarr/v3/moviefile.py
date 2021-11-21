#!/usr/bin/env python

from ..base import Manager


class MovieFile(Manager):
    def __init__(self, client):
        super().__init__(client)
        self.moviefile_path = "/moviefile"
        self.moviefile_id_path = "/moviefile/{id}".format(id="{id}")

    def get_moviefiles(self, ids):
        params = {"movieId": ids}
        return self.client.http_get(self.moviefile_path, params=params)

    # ID is the file ID, not the ID of the movie
    def get_moviefile_by_file_id(self, id):
        return self.client.http_get(self.moviefile_id_path.format(id=id))

    # ID is the file ID, not the ID of the movie
    def delete_moviefile(self, id):
        return self.client.http_delete(self.moviefile_id_path.format(id=id))
