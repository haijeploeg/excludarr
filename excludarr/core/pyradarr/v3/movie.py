#!/usr/bin/env python

from ..base import Manager


class Movie(Manager):
    def __init__(self, client):
        super().__init__(client)
        self.movie_path = "/movie"
        self.movie_id_path = "/movie/{id}".format(id="{id}")
        self.movie_lookup_path = "/movie/lookup"
        self.movie_editor_path = "/movie/editor"
        self.movie_import_path = "/movie/import"

    def get_all_movies(self):
        return self.client.http_get(self.movie_path)

    def get_movie_by_tmdbid(self, tmdb_id):
        params = {"tmdbid": tmdb_id}
        return self.client.http_get(self.movie_path, params=params)

    def add_movie(
        self,
        title,
        quality_profile_id,
        title_slug,
        images,
        tmdb_id,
        year,
        root_folder_path,
        path=None,
        monitored=True,
        search_for_movie=False,
    ):
        """
        TODO: figure out how to do this according to the documentation: https://radarr.video/docs/api/#/Movie/post_movie
        This is the old format, which works, but does not comply with the API v3 fomat.
        """

        json = {
            "title": title,
            "qualityProfileId": quality_profile_id,
            "titleSlug": title_slug,
            "images": images,
            "tmdbId": tmdb_id,
            "year": year,
            "path": path,
            "rootFolderPath": root_folder_path,
            "monitored": monitored,
            "addOptions": {"searchForMovie": search_for_movie},
        }
        return self.client.http_post(self.movie_path, json=json)

    def update_movie(self, updated_movie_dict, move_files=False):
        params = {"moveFiles": move_files}
        return self.client.http_put(
            self.movie_path, params=params, json=updated_movie_dict
        )

    def get_movie_by_id(self, id):
        return self.client.http_get(self.movie_id_path.format(id=id))

    def delete_movie(self, id, delete_files=False, add_import_exclusion=False):
        params = {
            "deleteFiles": delete_files,
            "addImportExclusion": add_import_exclusion,
        }
        return self.client.http_delete(self.movie_id_path.format(id=id), params=params)

    def lookup_movie(self, term):
        params = {"term": term}
        return self.client.http_get(self.movie_lookup_path, params=params)

    def update_movies(self, **kwargs):
        return self.client.http_put(self.movie_path, json=kwargs)

    def delete_movies(self, movie_ids, delete_files=False, add_import_exclusion=False):
        json = {
            "movieIds": movie_ids,
            "deleteFiles": delete_files,
            "addImportExclusion": add_import_exclusion,
        }
        return self.client.http_delete(self.movie_editor_path, json=json)

    def add_movies(self):
        """
        TODO: figure out how to do this properly
        """
        pass
