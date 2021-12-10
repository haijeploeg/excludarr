from ..base import Manager


class Episode(Manager):
    def __init__(self, client):
        super().__init__(client)
        self.episode_path = "/episode"
        self.episode_id_path = "/episode/{id}".format(id="{id}")

    def get_episodes_of_serie(self, series_id):
        params = {
            "seriesId": series_id,
        }
        return self.client.http_get(self.episode_path, params=params)

    def get_episode(self, id):
        return self.client.http_get(self.episode_id_path.format(id=id))

    def update_episode(self, id, updated_episode_dict):
        return self.client.http_put(self.episode_id_path.format(id=id), json=updated_episode_dict)
