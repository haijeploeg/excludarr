from loguru import logger
from rich.progress import Progress

import excludarr.modules.pysonarr as pysonarr
import excludarr.modules.pytmdb as pytmdb
import excludarr.utils.filters as filters

from excludarr.modules.justwatch import JustWatch
from excludarr.modules.justwatch.exceptions import JustWatchNotFound, JustWatchTooManyRequests


class SonarrActions:
    def __init__(self, url, api_key, locale, verify_ssl=False):
        logger.debug(f"Initializing PySonarr")
        self.sonarr_client = pysonarr.Sonarr(url, api_key, verify_ssl)

        logger.debug(f"Initializing JustWatch API with locale: {locale}")
        self.justwatch_client = JustWatch(locale)

    def _get_jw_serie_data(self, title, jw_entry):
        jw_id = jw_entry["id"]
        jw_serie_data = {}
        jw_imdb_ids = []
        jw_tmdb_ids = []

        try:
            logger.debug(f"Querying JustWatch API with ID: {jw_id} for title: {title}")
            jw_serie_data = self.justwatch_client.get_show(jw_id)

            jw_imdb_ids = filters.get_imdb_ids(jw_serie_data.get("external_ids", []))
            logger.debug(f"Got IMDB ID's: {jw_imdb_ids} from JustWatch API")

            jw_tmdb_ids = filters.get_tmdb_ids(jw_serie_data.get("external_ids", []))
            logger.debug(f"Got TMDB ID's: {jw_tmdb_ids} from JustWatch API")
        except JustWatchNotFound:
            logger.warning(f"Could not find title: {title} with JustWatch ID: {jw_id}")
        except JustWatchTooManyRequests:
            logger.error(f"JustWatch API returned 'Too Many Requests'")
            # TODO: Raise error so typer can abort properly

        return jw_serie_data, jw_imdb_ids, jw_tmdb_ids

    def _find_using_imdb_id(self, title, sonarr_id, imdb_id, fast, jw_query_payload={}):
        # Log the title and Sonarr ID
        logger.debug(
            f"Processing title: {title} with Sonarr ID: {sonarr_id} and IMDB ID: {imdb_id}"
        )

        # Log the JustWatch API call function
        logger.debug(f"Query JustWatch API with title: {title}")
        jw_query_data = self.justwatch_client.query_title(title, "show", fast, **jw_query_payload)

        for entry in jw_query_data["items"]:
            jw_id = entry["id"]
            jw_serie_data, jw_imdb_ids, _ = self._get_jw_serie_data(title, entry)

            # Break if the TMBD_ID in the query of JustWatch matches the one in Sonarr
            if imdb_id in jw_imdb_ids:
                logger.debug(f"Found JustWatch ID: {jw_id} for {title} with IMDB ID: {imdb_id}")
                return jw_id, jw_serie_data

        logger.debug(f"Could not find {title} using IMDB ID: {imdb_id}")
        return None, None

    def _find_using_tvdb_id(self, title, sonarr_id, tvdb_id, fast, jw_query_payload={}):
        # Log the title and Sonarr ID
        logger.debug(
            f"Processing title: {title} with Sonarr ID: {sonarr_id} and TVDB ID: {tvdb_id}"
        )

        # Log the JustWatch API call function
        logger.debug(f"Query JustWatch API with title: {title}")
        jw_query_data = self.justwatch_client.query_title(title, "show", fast, jw_query_payload)

        # Get TMDB ID from TMDB using the TVDB ID
        logger.debug(f"Trying to obtain the TMDB ID using TVDB ID: {tvdb_id} from TMDB API")
        tmdb_id = 0
        tmdb_find_result = self.tmdb.find.find_by_id(tvdb_id, "tvdb_id").get("tv_results", [])
        if tmdb_find_result:
            # Default to 0 if no ID is found
            tmdb_id = int(tmdb_find_result[0].get("id", 0))

        if tmdb_id != 0:
            for entry in jw_query_data["items"]:
                jw_id = entry["id"]
                jw_serie_data, _, jw_tmdb_ids = self._get_jw_serie_data(title, entry)

                # Break if the TMBD_ID in the query of JustWatch matches the one in Sonarr
                if tmdb_id in jw_tmdb_ids:
                    logger.debug(f"Found JustWatch ID: {jw_id} for {title} with TMDB ID: {tmdb_id}")
                    return jw_id, jw_serie_data

        else:
            logger.debug("Could not find a TMDB ID")

        logger.debug(f"Could not find {title} using TVDB ID: {tvdb_id}")
        return None, None

    def _find_serie(self, serie, jw_providers, tmdb_api_key, fast, exclude):
        # Set the minimal base variables
        sonarr_id = serie["id"]
        title = serie["title"]
        release_year = serie["year"]
        providers = [values["short_name"] for _, values in jw_providers.items()]

        # Set extra payload to narrow down the search if fast is true
        jw_query_payload = {}
        if fast:
            jw_query_payload = {
                "page_size": 3,
                "release_year_from": release_year,
                "release_year_until": release_year,
                "monetization_types": ["flatrate"],
            }
            if exclude:
                jw_query_payload.update({"providers": providers})

        # Check if there is an IMDB ID, otherwise check if TMDB API is reachable to get the TMDB ID of the movie
        imdb_id = serie.get("imdbId", None)
        tvdb_id = serie.get("tvdbId", None)
        logger.debug(f"{title} has IMDB ID: {imdb_id} and TVDB_ID: {tvdb_id}")

        # Set JustWatch return variables to None
        jw_id = None
        jw_serie_data = None

        # Setup TMDB if there is an API key provided
        # TODO: set to init
        if tmdb_api_key:
            self.tmdb = pytmdb.TMDB(tmdb_api_key)

        if imdb_id:
            # Try extracting the data by using the IMDB ID
            jw_id, jw_serie_data = self._find_using_imdb_id(
                title, sonarr_id, imdb_id, fast, jw_query_payload
            )
            if not jw_serie_data and tvdb_id and tmdb_api_key:
                logger.debug(f"Could not find {title} using IMDB, falling back to TMDB")
                jw_id, jw_serie_data = self._find_using_tvdb_id(title, sonarr_id, tvdb_id, fast)
        elif tvdb_id and tmdb_api_key:
            # If the user has filled in an TMDB ID fall back to querying TMDB API using the TVDB ID
            jw_id, jw_serie_data = self._find_using_tvdb_id(
                title, sonarr_id, tvdb_id, fast, jw_query_payload
            )
        else:
            # Skip this serie if no IMDB ID and TVDB ID are found
            logger.debug(
                f"No IMDB ID provided by Sonarr and no TMDB configuration set. Skipping serie: {title}"
            )

        return jw_id, jw_serie_data

    def get_series_to_exclude(
        self, providers, fast=True, disable_progress=False, tmdb_api_key=None
    ):
        exclude_series = {}

        # Get all series listed in Sonarr
        logger.debug("Getting all the series from Sonarr")
        sonarr_series = self.sonarr_client.serie.get_all_series()

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
            for serie in progress.track(sonarr_series):
                # Set the minimal base variables
                sonarr_id = serie["id"]
                title = serie["title"]
                filesize = serie.get("statistics", {}).get("sizeOnDisk", 0)
                release_year = serie["year"]
                ended = serie["ended"]

                # Get episodes of the serie
                episodes = self.sonarr_client.episode.get_episodes_of_serie(sonarr_id)

                # Get JustWatch serie data
                jw_id, jw_serie_data = self._find_serie(
                    serie, jw_providers, tmdb_api_key, fast, exclude=True
                )

                # Continue if the proper JustWatch ID is found
                if jw_serie_data:
                    logger.debug(f"Look up season data for {title}")
                    jw_seasons = jw_serie_data["seasons"]

                    # Loop over the seasons
                    for jw_season in jw_seasons:
                        jw_season_title = jw_season.get(
                            "title", f"Season {jw_season['season_number']}"
                        )
                        jw_season_id = jw_season["id"]
                        jw_season_data = self.justwatch_client.get_season(jw_season_id)
                        jw_episodes = jw_season_data.get("episodes", [])

                        logger.debug(f"Processing season {jw_season_title} of {title}")

                        # Loop over the episodes and check if there are providers
                        for episode in jw_episodes:
                            season_number = episode["season_number"]
                            episode_number = episode["episode_number"]

                            # Get episode providers
                            episode_providers = filters.get_jw_providers(episode)

                            # Check if the providers of the episodes matches the configured providers
                            providers_match = [
                                provider_details["clear_name"]
                                for provider_id, provider_details in jw_providers.items()
                                if provider_id in episode_providers.keys()
                            ]

                            if providers_match:
                                # Get the episode data from the information in Sonarr
                                sonarr_episode_data = filters.get_episode_data(
                                    episodes, season_number, episode_number
                                )
                                sonarr_episode_id = filters.get_episode_file_id(
                                    episodes, season_number, episode_number
                                )

                                exclude_series.update(
                                    {
                                        sonarr_id: {
                                            "title": title,
                                            "filesize": filesize,
                                            "release_year": release_year,
                                            "ended": ended,
                                            "jw_id": jw_id,
                                            "sonarr_object": serie,
                                            "sonarr_file_ids": exclude_series[sonarr_id][
                                                "sonarr_file_ids"
                                            ]
                                            + sonarr_episode_id
                                            if exclude_series.get(sonarr_id)
                                            else sonarr_episode_id,
                                            "episodes": exclude_series[sonarr_id]["episodes"]
                                            + [
                                                {
                                                    "season": season_number,
                                                    "episode": episode_number,
                                                    "providers": providers_match,
                                                    **sonarr_episode_data,
                                                }
                                            ]
                                            if exclude_series.get(sonarr_id)
                                            else [
                                                {
                                                    "season": season_number,
                                                    "episode": episode_number,
                                                    "providers": providers_match,
                                                    **sonarr_episode_data,
                                                }
                                            ],
                                        }
                                    }
                                )

                                logger.debug(
                                    f"{title} S{season_number}E{episode_number} is streaming on {', '.join(providers_match)}"
                                )

        # Check if the full season could be excluded rather than seperate episodes
        for exclude_id, exclude_entry in exclude_series.items():
            sonarr_object = exclude_entry["sonarr_object"]
            sonarr_seasons = sonarr_object["seasons"]
            exclude_episodes = exclude_entry["episodes"]

            seasons_to_exclude = []
            season_numbers = []

            # Loop over the seasons registerd in Sonarr
            for season in sonarr_seasons:
                sonarr_total_episodes = season["statistics"]["totalEpisodeCount"]
                sonarr_season_monitored = season["monitored"]
                sonarr_season_has_file = bool(season["statistics"]["episodeFileCount"])
                sonarr_season_number = int(season["seasonNumber"])

                # Get the total amount of episodes
                exclude_total_episodes = [
                    episode
                    for episode in exclude_episodes
                    if episode["season"] == sonarr_season_number
                ]

                # Get a list of providers of the season
                season_providers = [
                    episode["providers"]
                    for episode in exclude_episodes
                    if episode["season"] == sonarr_season_number
                ]
                season_providers = filters.flatten(season_providers)

                # Check if the amount of episodes to exclude is greater or equal the total episodes in Sonarr
                if len(exclude_total_episodes) >= sonarr_total_episodes:
                    season_numbers.append(sonarr_season_number)
                    seasons_to_exclude.append(
                        {
                            "season": sonarr_season_number,
                            "providers": season_providers,
                            "monitored": sonarr_season_monitored,
                            "has_file": sonarr_season_has_file,
                        }
                    )

            # Re order the exclude_series dict to strip the episodes if the whole season can be excluded
            updated_exclude_episodes = [
                episode for episode in exclude_episodes if episode["season"] not in season_numbers
            ]
            exclude_series[exclude_id]["episodes"] = updated_exclude_episodes
            exclude_series[exclude_id]["seasons"] = seasons_to_exclude
            exclude_series[exclude_id]["providers"] = filters.get_providers_from_seasons_episodes(
                exclude_entry["seasons"], exclude_entry["episodes"]
            )

        return exclude_series

    def get_series_to_re_add(self, providers, fast=True, disable_progress=False, tmdb_api_key=None):
        re_add_series = {}

        # Setup TMDB if there is an API key provided
        if tmdb_api_key:
            self.tmdb = pytmdb.TMDB(tmdb_api_key)

        # Get all series listed in Sonarr
        logger.debug("Getting all the series from Sonarr")
        sonarr_series = self.sonarr_client.serie.get_all_series()

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
            for serie in progress.track(sonarr_series):
                # Set the minimal base variables
                sonarr_id = serie["id"]
                title = serie["title"]
                release_year = serie["year"]
                ended = serie["ended"]

                # Get episodes of the serie
                episodes = self.sonarr_client.episode.get_episodes_of_serie(sonarr_id)

                # Get JustWatch serie data
                jw_id, jw_serie_data = self._find_serie(
                    serie, jw_providers, tmdb_api_key, fast, exclude=False
                )

                # Continue if the proper JustWatch ID is found
                if jw_serie_data:
                    logger.debug(f"Look up season data for {title}")
                    jw_seasons = jw_serie_data["seasons"]

                    # Loop over the seasons
                    for jw_season in jw_seasons:
                        jw_season_title = jw_season.get(
                            "title", f"Season {jw_season['season_number']}"
                        )
                        jw_season_id = jw_season["id"]
                        jw_season_data = self.justwatch_client.get_season(jw_season_id)
                        jw_episodes = jw_season_data.get("episodes", [])

                        logger.debug(f"Processing season {jw_season_title} of {title}")

                        # Loop over the episodes and check if there are providers
                        for episode in jw_episodes:
                            season_number = episode["season_number"]
                            episode_number = episode["episode_number"]

                            # Get episode providers
                            episode_providers = filters.get_jw_providers(episode)

                            # Check if the providers of the episodes matches the configured providers
                            providers_match = [
                                provider_details["clear_name"]
                                for provider_id, provider_details in jw_providers.items()
                                if provider_id in episode_providers.keys()
                            ]

                            if not providers_match:
                                # Get the episode data from the information in Sonarr
                                sonarr_episode_data = filters.get_episode_data(
                                    episodes, season_number, episode_number
                                )

                                re_add_series.update(
                                    {
                                        sonarr_id: {
                                            "title": title,
                                            "release_year": release_year,
                                            "ended": ended,
                                            "jw_id": jw_id,
                                            "sonarr_object": serie,
                                            "episodes": re_add_series[sonarr_id]["episodes"]
                                            + [
                                                {
                                                    "season": season_number,
                                                    "episode": episode_number,
                                                    **sonarr_episode_data,
                                                }
                                            ]
                                            if re_add_series.get(sonarr_id)
                                            else [
                                                {
                                                    "season": season_number,
                                                    "episode": episode_number,
                                                    **sonarr_episode_data,
                                                }
                                            ],
                                        }
                                    }
                                )

                                logger.debug(
                                    f"{title} S{season_number}E{episode_number} is not streaming on a configured provider"
                                )

        # Check if the full season could be excluded rather than seperate episodes
        for re_add_id, re_add_entry in re_add_series.items():
            sonarr_object = re_add_entry["sonarr_object"]
            sonarr_seasons = sonarr_object["seasons"]
            re_add_episodes = re_add_entry["episodes"]

            seasons_to_re_add = []
            season_numbers = []

            # Loop over the seasons registerd in Sonarr
            for season in sonarr_seasons:
                sonarr_total_episodes = season["statistics"]["totalEpisodeCount"]
                sonarr_season_monitored = season["monitored"]
                sonarr_season_number = int(season["seasonNumber"])

                # Get the total amount of episodes
                re_add_total_episodes = [
                    episode
                    for episode in re_add_episodes
                    if episode["season"] == sonarr_season_number
                ]

                # Check if the amount of episodes to exclude is greater or equals the total episodes in Sonarr
                if len(re_add_total_episodes) >= sonarr_total_episodes:
                    season_numbers.append(sonarr_season_number)
                    seasons_to_re_add.append(
                        {
                            "season": sonarr_season_number,
                            "monitored": sonarr_season_monitored,
                        }
                    )

            # Re order the re_add_series dict to strip the episodes if the whole season can be excluded
            # or if the episode is not monitored but the season is
            updated_re_add_episodes = []
            for episode in re_add_episodes:
                episode_season = episode["season"]
                episode_monitored = episode.get("monitored", True)
                season_monitored = [
                    season["monitored"]
                    for season in seasons_to_re_add
                    if season["season"] == episode_season
                ]

                if all(season_monitored) and not episode_monitored:
                    updated_re_add_episodes.append(episode)
                elif episode_season not in season_numbers:
                    updated_re_add_episodes.append(episode)

            # Save all episode IDs in case we need to re add the whole serie
            all_episode_ids = [
                episode["episode_id"]
                for episode in re_add_episodes
                if episode.get("episode_id", False)
            ]

            re_add_series[re_add_id]["all_episode_ids"] = all_episode_ids
            re_add_series[re_add_id]["episodes"] = updated_re_add_episodes
            re_add_series[re_add_id]["seasons"] = seasons_to_re_add

        return re_add_series

    def delete_serie(self, id, delete_files, add_import_exclusion):
        logger.debug("Starting the delete serie process")

        try:
            logger.debug(f"Deleting serie with Sonarr ID: {id}")
            self.sonarr_client.serie.delete_serie(
                id, delete_files=delete_files, add_import_exclusion=add_import_exclusion
            )
        except Exception as e:
            logger.error(e)
            logger.error(
                f"Something went wrong with deleting the serie from Sonarr, check the configuration or try --debug for more information"
            )

    def delete_episode_files(self, id, episode_file_ids):
        logger.debug(f"Starting the delete episodefile process")

        for episode_file in episode_file_ids:
            try:
                logger.debug(f"Deleting episode ID: {episode_file} for serie with Sonarr ID: {id}")
                self.sonarr_client.episodefile.delete_episodefile(episode_file)
            except Exception as e:
                logger.error(e)
                logger.error(
                    f"Something went wrong with deleting the episodefile with ID: {episode_file}, check the configuration or try --debug for more information"
                )

    def disable_monitored_serie(self, id, sonarr_object):
        logger.debug("Starting to disable monitoring on serie")

        sonarr_object["monitored"] = False

        try:
            logger.debug(f"Updating serie with Sonarr ID: {id}")
            self.sonarr_client.serie.update_serie(sonarr_object)
        except Exception as e:
            logger.error(e)
            logger.error(
                f"Something went wrong with updating the serie with ID: {id} in Sonarr, check the configuration or try --debug for more information"
            )

    def disable_monitored_seasons(self, id, sonarr_object, seasons):
        logger.debug("Starting to disable monitoring on seasons")

        updated_sonarr_object = filters.modify_sonarr_seasons(sonarr_object, seasons, False)

        try:
            logger.debug(f"Updating serie with Sonarr ID: {id}")
            self.sonarr_client.serie.update_serie(updated_sonarr_object)
        except Exception as e:
            logger.error(e)
            logger.error(
                f"Something went wrong with updating the serie with ID: {id} in Sonarr, check the configuration or try --debug for more information"
            )

    def disable_monitored_episodes(self, id, episode_ids):
        logger.debug("Starting to disable monitoring on episodes")

        for episode_id in episode_ids:
            try:
                logger.debug(
                    f"Get details of episode with ID: {episode_id} for serie with Sonarr ID: {id}"
                )
                episode_object = self.sonarr_client.episode.get_episode(episode_id)
                episode_object["monitored"] = False

                logger.debug(
                    f"Updating episode with ID: {episode_id} for serie with Sonarr ID: {id}"
                )
                self.sonarr_client.episode.update_episode(episode_id, episode_object)
            except Exception as e:
                logger.error(e)
                logger.error(
                    f"Something went wrong with updating the episode with ID: {episode_id} in Sonarr, check the configuration or try --debug for more information"
                )

    def enable_monitored_serie(self, id, sonarr_object):
        logger.debug("Starting to enable monitoring on serie")

        sonarr_object["monitored"] = True

        try:
            logger.debug(f"Updating serie with Sonarr ID: {id}")
            self.sonarr_client.serie.update_serie(sonarr_object)
        except Exception as e:
            logger.error(e)
            logger.error(
                f"Something went wrong with updating the serie with ID: {id} in Sonarr, check the configuration or try --debug for more information"
            )

    def enable_monitored_seasons(self, id, sonarr_object, seasons):
        logger.debug("Starting to enable monitoring on seasons")

        updated_sonarr_object = filters.modify_sonarr_seasons(sonarr_object, seasons, True)

        try:
            logger.debug(f"Updating serie with Sonarr ID: {id}")
            self.sonarr_client.serie.update_serie(updated_sonarr_object)
        except Exception as e:
            logger.error(e)
            logger.error(
                f"Something went wrong with updating the serie with ID: {id} in Sonarr, check the configuration or try --debug for more information"
            )

    def enable_monitored_episodes(self, id, episode_ids):
        logger.debug("Starting to enable monitoring on episodes")

        for episode_id in episode_ids:
            try:
                logger.debug(
                    f"Get details of episode with ID: {episode_id} for serie with Sonarr ID: {id}"
                )
                episode_object = self.sonarr_client.episode.get_episode(episode_id)
                episode_object["monitored"] = True

                logger.debug(
                    f"Updating episode with ID: {episode_id} for serie with Sonarr ID: {id}"
                )
                self.sonarr_client.episode.update_episode(episode_id, episode_object)
            except Exception as e:
                logger.error(e)
                logger.error(
                    f"Something went wrong with updating the episode with ID: {episode_id} in Sonarr, check the configuration or try --debug for more information"
                )
