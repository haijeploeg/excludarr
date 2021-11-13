#!/usr/bin/env python

from ..base import Manager


class Serie(Manager):
    def __init__(self, client):
        super().__init__(client)
        self.serie_path = "/series"
        self.serie_id_path = "/series/{id}".format(id="{id}")

    def get_all_series(self):
        return self.client.http_get(self.serie_path)

    def update_serie(self, updated_serie_dict):
        return self.client.http_put(self.serie_path, json=updated_serie_dict)

    def delete_serie(self, id, delete_files, add_import_exclusion):
        params = {
            "deleteFiles": delete_files,
            "addImportExclusion": add_import_exclusion,
        }
        return self.client.http_delete(self.serie_id_path.format(id=id), params=params)
