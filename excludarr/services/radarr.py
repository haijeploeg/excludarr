from pyarr import RadarrAPI

from excludarr.models import Movies


class Radarr:
    def __init__(self, url, api_key):
        self.client = RadarrAPI(url, api_key)
        
    def sync_all_to_db(self):
        movies = self.client.get_movie()
        
        for movie in movies:
            radarr_id = movie.get("id")
            title = movie.get("title")
            tmdb_id = movie.get("tmdbId")
            imdb_id = movie.get("imdbId")
            size = movie.get("sizeOnDisk")
            year = movie.get("year")
            quality_available = movie.get("movieFile", {}).get("quality", {}).get("quality", {}).get("name")
            poster = [x["remoteUrl"] for x in movie.get("images", {}) if x["coverType"] == "poster"][0]
            tags = movie.get("tags", [])
            monitored = movie.get("monitored", False)
            
            obj, created = Movies.objects.update_or_create(
                radarr_id=radarr_id,
                defaults={
                    "radarr_id": radarr_id,
                    "title": title,
                    "tmdb_id": tmdb_id,
                    "imdb_id": imdb_id,
                    "size": size,
                    "year": year,
                    "quality_available": quality_available,
                    "poster": poster,
                    "tags": tags,
                    "monitored": monitored
                }
            )
