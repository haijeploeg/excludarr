from ..base import Manager


class Movie(Manager):
    def get_details(self, movie_id):
        path = "/movie/{}".format(movie_id)

        return self.client.http_get(path)

    def get_watch_providers(self, movie_id):
        path = "/movie/{}/watch/providers".format(movie_id)

        return self.client.http_get(path)
