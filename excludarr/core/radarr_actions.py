from platform import release
from loguru import logger
from rich.progress import Progress

import excludarr.modules.pyradarr as pyradarr
import excludarr.utils.filters as filters

from excludarr.modules.justwatch import JustWatch
from excludarr.modules.justwatch.exceptions import JustWatchNotFound, JustWatchTooManyRequests
from excludarr.modules.pyradarr.exceptions import RadarrMovieNotFound


class RadarrActions:
    def __init__(self, url, api_key, locale, verify_ssl=False):
        logger.debug(f"Initializing PyRadarr")
        self.radarr_client = pyradarr.Radarr(url, api_key, verify_ssl)

        logger.debug(f"Initializing JustWatch API with locale: {locale}")
        self.justwatch_client = JustWatch(locale)

    def _get_jw_movie_data(self, title, jw_entry):
        jw_id = jw_entry["id"]
        jw_movie_data = {}
        jw_tmdb_ids = []

        try:
            logger.debug(f"Querying JustWatch API with ID: {jw_id} for title: {title}")
            jw_movie_data = self.justwatch_client.get_movie(jw_id)

            jw_tmdb_ids = filters.get_tmdb_ids(jw_movie_data.get("external_ids", []))
            logger.debug(f"Got TMDB ID's: {jw_tmdb_ids} from JustWatch API")
        except JustWatchNotFound:
            logger.warning(f"Could not find title: {title} with JustWatch ID: {jw_id}")
        except JustWatchTooManyRequests:
            logger.error(f"JustWatch API returned 'Too Many Requests'")
            # TODO: Raise error so typer can abort properly

        return jw_movie_data, jw_tmdb_ids

    def _find_movie(self, movie, jw_providers, fast, exclude):
        # Set the minimal base variables
        title = movie["title"]
        tmdb_id = movie["tmdbId"]
        release_year = filters.get_release_date(movie, format="%Y")
        providers = [values["short_name"] for _, values in jw_providers.items()]

        # Set extra payload to narrow down the search if fast is true
        jw_query_payload = {}
        if fast:
            jw_query_payload.update({"page_size": 3})

            if exclude:
                jw_query_payload.update(
                    {"monetization_types": ["flatrate"], "providers": providers}
                )

            if release_year:
                jw_query_payload.update(
                    {
                        "release_year_from": int(release_year),
                        "release_year_until": int(release_year),
                    }
                )

        # Log the JustWatch API call function
        logger.debug(f"Query JustWatch API with title: {title}")
        jw_query_data = self.justwatch_client.query_title(title, "movie", fast, **jw_query_payload)

        for entry in jw_query_data["items"]:
            jw_id = entry["id"]
            jw_movie_data, jw_tmdb_ids = self._get_jw_movie_data(title, entry)

            # Break if the TMBD_ID in the query of JustWatch matches the one in Radarr
            if tmdb_id in jw_tmdb_ids:
                logger.debug(f"Found JustWatch ID: {jw_id} for {title} with TMDB ID: {tmdb_id}")
                return jw_id, jw_movie_data

        return None, None

    def get_movies_to_exclude(self, providers, fast=True, disable_progress=False):
        exclude_movies = {}

        # Get all movies listed in Radarr
        logger.debug("Getting all the movies from Radarr")
        radarr_movies = self.radarr_client.movie.get_all_movies()

        # Get the providers listed for the configured locale from JustWatch
        # and filter it with the given providers. This will ensure only the correct
        # providers are in the dictionary.
        raw_jw_providers = self.justwatch_client.get_providers()
        jw_providers = filters.get_providers(raw_jw_providers, providers)
        logger.debug(
            f"Got the following providers: {', '.join([v['clear_name'] for _, v in jw_providers.items()])}"
        )

        progress = Progress(disable=disable_progress)
        with progress:
            for movie in progress.track(radarr_movies):
                # Set the minimal base variables
                radarr_id = movie["id"]
                title = movie["title"]
                tmdb_id = movie["tmdbId"]
                filesize = movie["sizeOnDisk"]
                release_date = filters.get_release_date(movie)

                # Log the title and Radarr ID
                logger.debug(
                    f"Processing title: {title} with Radarr ID: {radarr_id} and TMDB ID: {tmdb_id}"
                )

                # Find the movie
                jw_id, jw_movie_data = self._find_movie(movie, jw_providers, fast, exclude=True)

                if jw_movie_data:
                    # Get all the providers the movie is streaming on
                    movie_providers = filters.get_jw_providers(jw_movie_data)

                    # Loop over the configured providers and check if the provider
                    # matches the providers advertised at the movie. If a match is found
                    # update the exclude_movies dict
                    matched_providers = list(set(movie_providers.keys()) & set(jw_providers.keys()))

                    if matched_providers:
                        clear_names = [
                            provider_details["clear_name"]
                            for provider_id, provider_details in jw_providers.items()
                            if provider_id in matched_providers
                        ]

                        exclude_movies.update(
                            {
                                radarr_id: {
                                    "title": title,
                                    "filesize": filesize,
                                    "release_date": release_date,
                                    "radarr_object": movie,
                                    "tmdb_id": tmdb_id,
                                    "jw_id": jw_id,
                                    "providers": clear_names,
                                }
                            }
                        )

                        logger.debug(f"{title} is streaming on {', '.join(clear_names)}")

        return exclude_movies

    def get_movies_to_re_add(self, providers, fast=True, disable_progress=False):
        re_add_movies = {}

        # Get all movies listed in Radarr and filter it to only include not monitored movies
        logger.debug("Getting all the movies from Radarr")
        radarr_movies = self.radarr_client.movie.get_all_movies()
        radarr_not_monitored_movies = [movie for movie in radarr_movies if not movie["monitored"]]

        # Get the providers listed for the configured locale from JustWatch
        # and filter it with the given providers. This will ensure only the correct
        # providers are in the dictionary.
        raw_jw_providers = self.justwatch_client.get_providers()
        jw_providers = filters.get_providers(raw_jw_providers, providers)
        logger.debug(
            f"Got the following providers: {', '.join([v['clear_name'] for _, v in jw_providers.items()])}"
        )

        progress = Progress(disable=disable_progress)
        with progress:
            for movie in progress.track(radarr_not_monitored_movies):
                # Set the minimal base variables
                radarr_id = movie["id"]
                title = movie["title"]
                tmdb_id = movie["tmdbId"]
                release_date = filters.get_release_date(movie)

                # Log the title and Radarr ID
                logger.debug(
                    f"Processing title: {title} with Radarr ID: {radarr_id} and TMDB ID: {tmdb_id}"
                )

                # Find the movie
                jw_id, jw_movie_data = self._find_movie(movie, jw_providers, fast, exclude=False)

                if jw_movie_data:
                    # Get all the providers the movie is streaming on
                    movie_providers = filters.get_jw_providers(jw_movie_data)

                    # Check if the JustWatch providers matching the movie providers
                    matched_providers = list(set(movie_providers.keys()) & set(jw_providers.keys()))

                    if not matched_providers:
                        re_add_movies.update(
                            {
                                radarr_id: {
                                    "title": title,
                                    "release_date": release_date,
                                    "radarr_object": movie,
                                    "tmdb_id": tmdb_id,
                                    "jw_id": jw_id,
                                }
                            }
                        )
                        logger.debug(f"{title} is not streaming on a configured provider")

        return re_add_movies

    def delete(self, ids, delete_files, add_import_exclusion):
        logger.debug("Starting the delete process")

        try:
            logger.debug("Trying to bulk delete all movies at once")

            self.radarr_client.movie.delete_movies(
                ids, delete_files=delete_files, add_import_exclusion=add_import_exclusion
            )
        except RadarrMovieNotFound:
            logger.warning("Bulk delete failed, falling back to deleting each movie individually")
            for id in ids:
                logger.debug(f"Deleting movie with Radarr ID: {id}")

                self.radarr_client.movie.delete_movie(
                    id, delete_files=delete_files, add_import_exclusion=add_import_exclusion
                )
        except Exception as e:
            logger.error(e)
            logger.error(
                f"Something went wrong with deleting the movies from Radarr, check the configuration or try --debug for more information"
            )

    def disable_monitored(self, movies):
        logger.debug("Starting the process of changing the status to not monitored")
        for movie in movies:
            movie.update({"monitored": False})

            logger.debug(f"Change monitored to False for movie with Radarr ID: {movie['id']}")
            self.radarr_client.movie.update_movie(movie)

    def enable_monitored(self, movies):
        logger.debug("Starting the process of changing the status to monitored")
        for movie in movies:
            movie.update({"monitored": True})

            logger.debug(f"Change monitored to True for movie with Radarr ID: {movie['id']}")
            self.radarr_client.movie.update_movie(movie)

    def delete_files(self, ids):
        logger.debug("Starting the process of deleting the files")
        for id in ids:
            logger.debug(f"Checking if movie with Radarr ID: {id} has files")
            moviefiles = self.radarr_client.moviefile.get_moviefiles(id)

            for moviefile in moviefiles:
                logger.debug(f"Deleting files for movie with Radarr ID: {id}")
                self.radarr_client.moviefile.delete_moviefile(moviefile["id"])
