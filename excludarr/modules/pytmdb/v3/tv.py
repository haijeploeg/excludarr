from ..base import Manager


class TV(Manager):
    def get_details(self, tv_id):
        path = "/tv/{}".format(tv_id)

        return self.client.http_get(path)

    def get_watch_providers(self, tv_id):
        path = "/tv/{}/watch/providers".format(tv_id)

        return self.client.http_get(path)
