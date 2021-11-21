from loguru import logger

from modules.justwatch.exceptions import JustWatchNotFound, JustWatchTooManyRequests
from modules.justwatch import JustWatch

import modules.pyradarr as pyradarr

import utils.filters as filters

from pprint import pprint


class RadarrActions:
    def __init__(self, url, api_key, locale, verify_ssl=False):
        logger.debug(f"Initializing PyRadarr")
        self.radarr_client = pyradarr.Radarr(url, api_key, verify_ssl)

        logger.debug(f"Initializing JustWatch API with locale: {locale}")
        self.justwatch_client = JustWatch(locale)

    def get_movies_to_exclude(self, providers):
        exclude_movies = {}

        # Get all movies listed in Radarr
        logger.debug("Getting all the movies from Radarr")
        radarr_movies = self.radarr_client.movie.get_all_movies()

        # Get the providers listed for the configured locale from JustWatch
        # and filter it with the given providers. This will ensure only the correct
        # providers are in the dictionary.
        raw_jw_providers = self.justwatch_client.get_providers()
        jw_providers = filters.get_jw_providers(raw_jw_providers, providers)
        logger.debug(
            f"Matched the following providers: {', '.join([v['clear_name'] for _, v in jw_providers.items()])}"
        )

        for movie in radarr_movies:
            radarr_id = movie["id"]
            title = movie["title"]
            tmdb_id = movie["tmdbId"]

            logger.debug(f"Query JustWatch API with title: {title}")
            jw_query_data = self.justwatch_client.query_title(title, "movie")

            for entry in jw_query_data["items"]:
                jw_id = entry["id"]

                try:
                    jw_movie_data = self.justwatch_client.get_movie(jw_id)
                    jw_tmdb_id = filters.get_tmdb_id(
                        jw_movie_data.get("external_ids", [])
                    )
                except JustWatchNotFound:
                    logger.warning(
                        f"Could not find movie: {title} with JustWatch ID: {jw_id}"
                    )
                except JustWatchTooManyRequests:
                    logger.error(f"JustWatch API returned 'Too Many Requests'")

                # Break if the TMBD_ID in the query of JustWatch matches the one in Radarr
                if tmdb_id == jw_tmdb_id:
                    logger.debug(
                        f"Found JustWatch ID: {jw_id} for {title} with TMDB ID {tmdb_id}"
                    )
                    break

            # Get all the providers the movie is streaming on
            movie_providers = filters.get_jw_movie_providers(jw_movie_data)

            # Loop over the configured providers and check if the provider
            # matches the providers advertised at the movie. If a match is found
            # update the exclude_movies dict
            for provider_id, provider_details in jw_providers.items():
                clear_name = provider_details["clear_name"]

                if provider_id in movie_providers.keys():

                    exclude_movies.update(
                        {
                            radarr_id: {
                                "title": title,
                                "tmdb_id": tmdb_id,
                                "jw_id": jw_id,
                                "providers": exclude_movies[radarr_id]["providers"]
                                + [clear_name]
                                if exclude_movies.get(radarr_id)
                                else [clear_name],
                            }
                        }
                    )

                    logger.debug(f"{title} is streaming on {clear_name}")

        return exclude_movies

    def delete(self, delete_files, add_import_exclusion):
        pass

    def change_status(self, status):
        pass
