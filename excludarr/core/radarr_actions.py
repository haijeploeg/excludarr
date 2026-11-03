from typing import Collection, List
from loguru import logger
from rich.progress import Progress
from pyarr import RadarrAPI

from .utils.filter_entries import filter_entries

import excludarr.utils.filters as filters

from excludarr.modules.justwatch import JustWatch


class RadarrActions:
    def __init__(self, url, api_key, locale):
        logger.debug("Initializing PyRadarr")
        self.radarr_client = RadarrAPI(url, api_key)

        logger.debug(f"Initializing JustWatch API with locale: {locale}")
        self.justwatch_client = JustWatch(locale)

    def _find_movie(self, movie, jw_providers, fast, exclude):
        # Set the minimal base variables
        title = movie["title"]
        tmdb_id = movie["tmdbId"]
        imdb_id = movie["imdbId"] if "imdbId" in movie else None
        release_year = filters.get_release_date(movie, format="%Y")
        providers = [
            values["short_name"] for _, values in jw_providers.items()
        ]

        # Set extra payload to narrow down the search if fast is true
        jw_query_payload = {}
        if fast:
            jw_query_payload.update({"page_size": 3})

            if exclude:
                jw_query_payload.update(
                    {
                        "monetization_types": ["flatrate"],
                        "providers": providers,
                    }
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
        titles = self.justwatch_client.search_movie(title)

        if titles:
            for entry in titles:
                jw_imdb_id = entry.imdbId
                jw_tmdb_id = entry.tmdbId

                # TODO: maybe also check year
                if (imdb_id is not None and imdb_id == jw_imdb_id) or (
                    tmdb_id is not None and tmdb_id == jw_tmdb_id
                ):
                    logger.debug(
                        f"Found JustWatch IMDB ID: {jw_imdb_id} for {title} with Radarr IMDB ID: {imdb_id}"  # noqa: E501
                    )

                    # TODO: implement fast

                    # search providers
                    offers = self.justwatch_client.query_movie_offers(
                        entry.id, providers
                    )

                    return (entry, offers)
        logger.debug(f"Not found title: {title}")
        return None

    def get_movies_to_exclude(
        self,
        bl_movies: List,
        bl_tags: List,
        providers,
        fast=True,
        disable_progress=False,
    ):
        exclude_movies = {}

        # Get all movies listed in Radarr
        logger.debug("Getting all the movies from Radarr")
        radarr_movies: Collection = self.radarr_client.get_movie()

        movies_cnt = len(radarr_movies)

        logger.debug(
            "Filtering the movies from Radarr with the provided blacklists"
        )
        radarr_movies = filter_entries(
            self.radarr_client, radarr_movies, bl_movies, bl_tags
        )

        logger.debug(
            f"Done filtering movies, before: {movies_cnt}, after: {len(radarr_movies)}"  # noqa: E501
        )
        # exit()

        # Get the providers listed for the configured locale from JustWatch
        # and filter it with the given providers. This will ensure only the
        # correct providers are in the dictionary.
        jw_providers = filters.get_providers(
            self.justwatch_client.get_providers(), providers
        )

        logger.debug(
            f"Got the following providers: {', '.join([v['clear_name'] for _, v in jw_providers.items()])}"  # noqa: E501
        )

        progress = Progress(disable=disable_progress)
        with progress:
            for movie in progress.track(radarr_movies):
                # Set the minimal base variables
                radarr_id = movie["id"]
                title = movie["title"]
                tmdb_id = movie["tmdbId"] if "tmdbId" in movie else None
                imdb_id = movie["imdbId"] if "imdbId" in movie else None
                filesize = movie["sizeOnDisk"]
                release_date = filters.get_release_date(movie)

                # Log the title and Radarr ID
                logger.debug(
                    f"Processing title: {title} with Radarr ID: {radarr_id} and IMDB ID: {imdb_id}"  # noqa: E501
                )

                # Find the movie
                find_res = self._find_movie(
                    movie, jw_providers, fast, exclude=True
                )
                if find_res is None:
                    continue

                (found_movie, offers) = find_res

                if found_movie is None or offers is None or len(offers) == 0:
                    continue

                # Get all the providers the movie is streaming on
                movie_providers = filters.get_jw_providers(offers)

                # Loop over the configured providers and check if the provider
                # matches the providers advertised at the movie. If a match is
                # found update the exclude_movies dict
                matched_providers = list(
                    set(movie_providers.keys()) & set(jw_providers.keys())
                )

                if matched_providers is None:
                    continue

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
                            "jw_id": found_movie.id,
                            "imdb_id": imdb_id,
                            "providers": clear_names,
                        }
                    }
                )

                logger.debug(
                    f"{title} is streaming on {', '.join(clear_names)}"
                )

        logger.debug("Done searching movies to exclude.")

        return exclude_movies

    def get_movies_to_re_add(
        self,
        bl_movies: List,
        bl_tags: List,
        providers,
        fast=True,
        disable_progress=False,
    ):
        re_add_movies = {}

        # Get all movies listed in Radarr and filter it to only include not
        # monitored movies
        logger.debug("Getting all the movies from Radarr")
        radarr_movies: Collection = self.radarr_client.get_movie()

        movies_cnt = len(radarr_movies)

        logger.debug(
            "Filtering the movies from Radarr with the provided blacklists"
        )
        radarr_movies = filter_entries(
            self.radarr_client,
            radarr_movies,
            bl_movies,
            bl_tags,
            monitored=False,
        )

        logger.debug(
            f"Done filtering movies, before: {movies_cnt}, after: {len(radarr_movies)}"  # noqa: E501
        )

        # Get the providers listed for the configured locale from JustWatch
        # and filter it with the given providers. This will ensure only the
        # correct providers are in the dictionary.
        raw_jw_providers = self.justwatch_client.get_providers()
        jw_providers = filters.get_providers(raw_jw_providers, providers)
        logger.debug(
            f"Got the following providers: {', '.join([v['clear_name'] for _, v in jw_providers.items()])}"  # noqa: E501
        )

        progress = Progress(disable=disable_progress)
        with progress:
            for movie in progress.track(radarr_movies):
                # Set the minimal base variables
                radarr_id = movie["id"]
                title = movie["title"]
                tmdb_id = movie["tmdbId"] if "tmdbId" in movie else None
                imdb_id = movie["imdbId"] if "imdbId" in movie else None
                release_date = filters.get_release_date(movie)

                # Log the title and Radarr ID
                logger.debug(
                    f"Processing title: {title} with Radarr ID: {radarr_id} and IMDB ID: {imdb_id}"  # noqa: E501
                )

                # Find the movie
                find_res = self._find_movie(
                    movie, jw_providers, fast, exclude=True
                )
                if find_res is None:
                    continue

                (found_movie, offers) = find_res

                logger.debug(f"{found_movie=}")
                logger.debug(f"{offers=}")

                if found_movie is None or offers is None or len(offers) != 0:
                    continue

                # Get all the providers the movie is streaming on
                movie_providers = filters.get_jw_providers(offers)

                # Check if the JustWatch providers matching the movie providers
                matched_providers = list(
                    set(movie_providers.keys()) & set(jw_providers.keys())
                )

                if matched_providers is None:
                    continue

                re_add_movies.update(
                    {
                        radarr_id: {
                            "title": title,
                            "release_date": release_date,
                            "radarr_object": movie,
                            "tmdb_id": tmdb_id,
                            "imdb_id": imdb_id,
                            "jw_id": found_movie.id,
                        }
                    }
                )
                logger.debug(
                    f"{title} is not streaming on a configured provider"
                )

        return re_add_movies

    def delete(self, ids, delete_files, add_import_exclusion):
        logger.debug("Starting the delete process")

        try:
            logger.debug("Trying to bulk delete all movies at once")

            self.radarr_client.del_movies(
                {
                    "movieIds": ids,
                    "deleteFiles": delete_files,
                    "addImportExclusion": add_import_exclusion,
                }
            )
        except Exception:
            logger.warning(
                "Bulk delete failed, falling back to deleting each movie individually"  # noqa: E501
            )

            try:
                for id in ids:
                    logger.debug(f"Deleting movie with Radarr ID: {id}")

                    self.radarr_client.del_movie(
                        id,
                        delete_files=delete_files,
                        add_exclusion=add_import_exclusion,
                    )
            except Exception as e:
                logger.error(e)
                logger.error(
                    "Something went wrong with deleting the movies from Radarr, check the configuration or try --debug for more information"  # noqa: E501
                )

    def disable_monitored(self, movies):
        logger.debug(
            "Starting the process of changing the status to not monitored"
        )
        for movie in movies:
            movie.update({"monitored": False})

            logger.debug(
                f"Change monitored to False for movie with Radarr ID: {movie['id']}"  # noqa: E501
            )
            self.radarr_client.upd_movie(movie)

    def enable_monitored(self, movies):
        logger.debug(
            "Starting the process of changing the status to monitored"
        )
        for movie in movies:
            movie.update({"monitored": True})

            logger.debug(
                f"Change monitored to True for movie with Radarr ID: {movie['id']}"  # noqa: E501
            )
            self.radarr_client.upd_movie(movie)

    def delete_files(self, ids):
        logger.debug("Starting the process of deleting the files")
        for id in ids:
            logger.debug(f"Checking if movie with Radarr ID: {id} has files")
            moviefiles = self.radarr_client.get_movie_files_by_movie_id(id)

            for moviefile in moviefiles:
                logger.debug(f"Deleting files for movie with Radarr ID: {id}")
                self.radarr_client.del_movie_file(moviefile["id"])
