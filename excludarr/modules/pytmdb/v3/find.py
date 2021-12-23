from ..base import Manager


class Find(Manager):
    def find_by_id(self, external_id, external_source):
        path = "/find/{}".format(external_id)

        params = {"external_source": external_source}
        return self.client.http_get(path, params=params)
