from typing import Collection, Dict, List
from loguru import logger
from rich.progress import Progress
from pyarr import SonarrAPI

from excludarr.core.utils.filter_entries import filter_entries
import excludarr.modules.pytmdb as pytmdb
import excludarr.utils.filters as filters

from excludarr.modules.justwatch import JustWatch


class SonarrActions:
    sonarr_client: SonarrAPI
    justwatch_client: JustWatch

    def __init__(self, url, api_key, locale):
        logger.debug("Initializing PySonarr")
        self.sonarr_client = SonarrAPI(url, api_key, ver_uri="/v3")

        logger.debug(f"Initializing JustWatch API with locale: {locale}")
        self.justwatch_client = JustWatch(locale)

    def _find_using_imdb_id(
        self, title, sonarr_id, imdb_id, fast, jw_query_payload={}
    ):
        # Log the title and Sonarr ID
        logger.debug(
            f"Processing title: {title} with Sonarr ID: {sonarr_id} and IMDB ID: {imdb_id}"  # noqa: E501
        )

        # Log the JustWatch API call function
        logger.debug(f"Query JustWatch API with title: {title}")
        shows = self.justwatch_client.search_show(title)

        if shows:
            for entry in shows:
                jw_id = entry.id
                jw_imdb_ids = entry.imdbId

                logger.debug(f"{title} - {jw_id} - {jw_imdb_ids}")

                # Break if the TMBD_ID in the query of JustWatch matches the
                # one in Sonarr
                if jw_imdb_ids is not None and imdb_id in jw_imdb_ids:
                    logger.debug(
                        f"Found JustWatch ID: {jw_id} for {title} with IMDB ID: {imdb_id}"  # noqa: E501
                    )
                    return entry

        logger.debug(f"Could not find {title} using IMDB ID: {imdb_id}")
        return None

    def _find_using_tvdb_id(
        self,
        title,
        sonarr_id,
        tvdb_id,
        fast,
        jw_query_payload={},
    ):

        # Log the title and Sonarr ID
        logger.debug(
            f"Processing title: {title} with Sonarr ID: {sonarr_id} and TVDB ID: {tvdb_id}"  # noqa: E501
        )

        # Log the JustWatch API call function
        logger.debug(f"Query JustWatch API with title: {title}")

        jw_shows = self.justwatch_client.search_show(title)

        # Get TMDB ID from TMDB using the TVDB ID
        logger.debug(
            f"Trying to obtain the TMDB ID using TVDB ID: {tvdb_id} from TMDB API"  # noqa: E501
        )
        tmdb_id = 0
        tmdb_find_result = self.tmdb.find.find_by_id(tvdb_id, "tvdb_id").get(
            "tv_results", []
        )
        if tmdb_find_result:
            # Default to 0 if no ID is found
            tmdb_id = int(tmdb_find_result[0].get("id", 0))

        if tmdb_id != 0:
            if jw_shows:
                for entry in jw_shows:
                    jw_id = entry.id
                    jw_tmdb_id = entry.tmdbId

                    # Break if the TMBD_ID in the query of JustWatch matches
                    # the one in Sonarr
                    if tmdb_id == jw_tmdb_id:
                        logger.debug(
                            f"Found JustWatch ID: {jw_id} for {title} with TMDB ID: {tmdb_id}"  # noqa: E501
                        )
                        return entry

        else:
            logger.debug("Could not find a TMDB ID")

        logger.debug(f"Could not find {title} using TVDB ID: {tvdb_id}")
        return None

    def _find_serie(self, serie, jw_providers, tmdb_api_key, fast, exclude):
        # Set the minimal base variables
        sonarr_id = serie["id"]
        title = serie["title"]
        release_year = serie["year"]
        providers = [
            values["short_name"] for _, values in jw_providers.items()
        ]

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

        # Check if there is an IMDB ID, otherwise check if TMDB API is
        # reachable to get the TMDB ID of the movie
        imdb_id = serie.get("imdbId", None)
        tvdb_id = serie.get("tvdbId", None)
        logger.debug(f"{title} has IMDB ID: {imdb_id} and TVDB_ID: {tvdb_id}")

        # Set JustWatch return variables to None
        show = None
        offers = None

        # Setup TMDB if there is an API key provided
        # TODO: set to init
        if tmdb_api_key:
            self.tmdb = pytmdb.TMDB(tmdb_api_key)

        if imdb_id:
            # Try extracting the data by using the IMDB ID
            show = self._find_using_imdb_id(
                title, sonarr_id, imdb_id, fast, jw_query_payload
            )
            if not show and tvdb_id and tmdb_api_key:
                logger.debug(
                    f"Could not find {title} using IMDB, falling back to TMDB"
                )
                show = self._find_using_tvdb_id(
                    title, sonarr_id, tvdb_id, fast
                )
        elif tvdb_id and tmdb_api_key:
            # If the user has filled in an TMDB ID fall back to querying
            # TMDB API using the TVDB ID
            show = self._find_using_tvdb_id(
                title, sonarr_id, tvdb_id, fast, jw_query_payload
            )
        else:
            # Skip this serie if no IMDB ID and TVDB ID are found
            logger.debug(
                f"No IMDB ID provided by Sonarr and no TMDB configuration set. Skipping serie: {title}"  # noqa: E501
            )

        if show:
            # TODO: implement forceFlatrate flag
            offers = self.justwatch_client.query_show_offers(
                show.id, providers, True
            )

        return show, offers

    def get_series_to_exclude(
        self,
        bl_series: List,
        bl_tags: List,
        providers,
        fast=True,
        disable_progress=False,
        tmdb_api_key=None,
    ):
        exclude_series: Dict = {}

        # Get all series listed in Sonarr
        logger.debug("Getting all the series from Sonarr")
        sonarr_series: Collection = self.sonarr_client.get_series()

        series_cnt = len(sonarr_series)

        logger.debug(
            "Filtering the movies from Radarr with the provided blacklists"
        )
        sonarr_series = filter_entries(
            self.sonarr_client, sonarr_series, bl_series, bl_tags
        )

        logger.debug(
            f"Done filtering movies, before: {series_cnt}, after: {len(sonarr_series)}"  # noqa: E501
        )

        # Get the providers listed for the configured locale from JustWatch
        # and filter it with the given providers. This will ensure only the
        # correct providers are in the dictionary.
        raw_jw_providers = self.justwatch_client.get_providers()
        jw_providers = filters.get_providers(raw_jw_providers, providers)
        logger.debug(
            f"Got the following providers: {', '.join([v['clear_name'] for _, v in jw_providers.items()])}"  # noqa: E501
        )

        # TODO: fix this block of code using early exits instead of indenting
        #       this much
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
                episodes = self.sonarr_client.get_episode(sonarr_id, True)

                # Get JustWatch serie data
                (show, offers) = self._find_serie(
                    serie, jw_providers, tmdb_api_key, fast, exclude=True
                )

                # Continue if the proper JustWatch ID is found
                if show is None or offers is None or len(offers) == 0:
                    continue
                logger.debug(f"Look up season data for {title}")

                # Loop over the seasons
                for jw_season_idx, jw_season in offers.items():

                    logger.debug(
                        f"Processing season {jw_season_idx} of {title}"
                    )

                    # Loop over the episodes and check if there are
                    # providers
                    for jw_episode_idx, jw_episode in jw_season.items():
                        season_number = jw_season_idx
                        episode_number = jw_episode_idx

                        # Get episode providers
                        episode_providers = filters.get_jw_providers(
                            jw_episode
                        )

                        # Check if the providers of the episodes matches
                        # the configured providers
                        providers_match = [
                            provider_details["clear_name"]
                            for provider_id, provider_details in jw_providers.items()  # noqa: E501
                            if provider_id in episode_providers.keys()
                        ]

                        if not providers_match:
                            continue
                        # Get the episode data from the information in
                        # Sonarr
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
                                    "jw_id": show.id,
                                    "sonarr_object": serie,
                                    "sonarr_file_ids": (
                                        exclude_series[sonarr_id][
                                            "sonarr_file_ids"
                                        ]
                                        + sonarr_episode_id
                                        if exclude_series.get(sonarr_id)
                                        else sonarr_episode_id
                                    ),
                                    "episodes": (
                                        exclude_series[sonarr_id]["episodes"]
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
                                        ]
                                    ),
                                }
                            }
                        )

                        logger.debug(
                            f"{title} S{season_number}E{episode_number} is streaming on {', '.join(providers_match)}"  # noqa: E501
                        )

        # Check if the full season could be excluded rather than seperate
        # episodes
        for exclude_id, exclude_entry in exclude_series.items():
            sonarr_object = exclude_entry["sonarr_object"]
            sonarr_seasons = sonarr_object["seasons"]
            exclude_episodes = exclude_entry["episodes"]

            seasons_to_exclude = []
            season_numbers = []

            # Loop over the seasons registerd in Sonarr
            for season in sonarr_seasons:
                sonarr_total_episodes = season["statistics"][
                    "totalEpisodeCount"
                ]
                sonarr_season_monitored = season["monitored"]
                sonarr_season_has_file = bool(
                    season["statistics"]["episodeFileCount"]
                )
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

                # Check if the amount of episodes to exclude is greater or
                # equal the total episodes in Sonarr
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

            # Re order the exclude_series dict to strip the episodes if the
            # whole season can be excluded
            updated_exclude_episodes = [
                episode
                for episode in exclude_episodes
                if episode["season"] not in season_numbers
            ]
            exclude_series[exclude_id]["episodes"] = updated_exclude_episodes
            exclude_series[exclude_id]["seasons"] = seasons_to_exclude
            exclude_series[exclude_id]["providers"] = (
                filters.get_providers_from_seasons_episodes(
                    exclude_entry["seasons"], exclude_entry["episodes"]
                )
            )

        logger.debug("Done searching series to exclude.")

        return exclude_series

    def get_series_to_re_add(
        self,
        bl_series: List,
        bl_tags: List,
        providers,
        fast=True,
        disable_progress=False,
        tmdb_api_key=None,
    ):
        re_add_series: Dict = {}

        # Setup TMDB if there is an API key provided
        if tmdb_api_key:
            self.tmdb = pytmdb.TMDB(tmdb_api_key)

        # Get all series listed in Sonarr
        logger.debug("Getting all the series from Sonarr")
        sonarr_series: Collection = self.sonarr_client.get_series()

        series_cnt = len(sonarr_series)

        logger.debug(
            "Filtering the movies from Radarr with the provided blacklists"
        )
        sonarr_series = filter_entries(
            self.sonarr_client, sonarr_series, bl_series, bl_tags
        )

        logger.debug(
            f"Done filtering movies, before: {series_cnt}, after: {len(sonarr_series)}"  # noqa: E501
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
            for serie in progress.track(sonarr_series):
                # Set the minimal base variables
                sonarr_id = serie["id"]
                title = serie["title"]
                release_year = serie["year"]
                ended = serie["ended"]

                # Get episodes of the serie
                episodes = self.sonarr_client.get_episode(sonarr_id, True)

                # Get JustWatch serie data
                (show, offers) = self._find_serie(
                    serie, jw_providers, tmdb_api_key, fast, exclude=True
                )

                # Continue if the proper JustWatch ID is found
                if show is None or offers is None or len(offers) == 0:
                    continue

                logger.debug(f"Look up season data for {title}")

                # Loop over the seasons
                for jw_season_idx, jw_season in offers.items():

                    logger.debug(
                        f"Processing season {jw_season_idx} of {title}"
                    )

                    # Loop over the episodes and check if there are providers
                    for jw_episode_idx, jw_episode in jw_season.items():
                        season_number = jw_season_idx
                        episode_number = jw_episode_idx

                        # Get episode providers
                        episode_providers = filters.get_jw_providers(
                            jw_episode
                        )

                        # Check if the providers of the episodes matches the
                        # configured providers
                        providers_match = [
                            provider_details["clear_name"]
                            for provider_id, provider_details in jw_providers.items()  # noqa: E501
                            if provider_id in episode_providers.keys()
                        ]

                        if providers_match:
                            continue

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
                                    "jw_id": show.id,
                                    "sonarr_object": serie,
                                    "episodes": (
                                        re_add_series[sonarr_id]["episodes"]
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
                                        ]
                                    ),
                                }
                            }
                        )

                        logger.debug(
                            f"{title} S{season_number}E{episode_number} is not streaming on a configured provider"  # noqa: E501
                        )

        # Check if the full season could be excluded rather than seperate
        # episodes
        for re_add_id, re_add_entry in re_add_series.items():
            sonarr_object = re_add_entry["sonarr_object"]
            sonarr_seasons = sonarr_object["seasons"]
            re_add_episodes = re_add_entry["episodes"]

            seasons_to_re_add = []
            season_numbers = []

            # Loop over the seasons registerd in Sonarr
            for season in sonarr_seasons:
                sonarr_total_episodes = season["statistics"][
                    "totalEpisodeCount"
                ]
                sonarr_season_monitored = season["monitored"]
                sonarr_season_number = int(season["seasonNumber"])

                # Get the total amount of episodes
                re_add_total_episodes = [
                    episode
                    for episode in re_add_episodes
                    if episode["season"] == sonarr_season_number
                ]

                # Check if the amount of episodes to exclude is greater or
                # equals the total episodes in Sonarr
                if len(re_add_total_episodes) >= sonarr_total_episodes:
                    season_numbers.append(sonarr_season_number)
                    seasons_to_re_add.append(
                        {
                            "season": sonarr_season_number,
                            "monitored": sonarr_season_monitored,
                        }
                    )

            # Re order the re_add_series dict to strip the episodes if the
            # whole season can be excluded or if the episode is not monitored
            # but the season is
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
            self.sonarr_client.del_series(id, delete_files=delete_files)
        except Exception as e:
            logger.error(e)
            logger.error(
                "Something went wrong with deleting the serie from Sonarr, check the configuration or try --debug for more information"  # noqa: E501
            )

    def delete_episode_files(self, id, episode_file_ids):
        logger.debug("Starting the delete episodefile process")

        for episode_file in episode_file_ids:
            try:
                logger.debug(
                    f"Deleting episode ID: {episode_file} for serie with Sonarr ID: {id}"  # noqa: E501
                )
                self.sonarr_client.del_episode_file(episode_file)
            except Exception as e:
                logger.error(e)
                logger.error(
                    f"Something went wrong with deleting the episodefile with ID: {episode_file}, check the configuration or try --debug for more information"  # noqa: E501
                )

    def disable_monitored_serie(self, id, sonarr_object):
        logger.debug("Starting to disable monitoring on serie")

        sonarr_object["monitored"] = False

        try:
            logger.debug(f"Updating serie with Sonarr ID: {id}")
            self.sonarr_client.upd_series(sonarr_object)
        except Exception as e:
            logger.error(e)
            logger.error(
                f"Something went wrong with updating the serie with ID: {id} in Sonarr, check the configuration or try --debug for more information"  # noqa: E501
            )

    def disable_monitored_seasons(self, id, sonarr_object, seasons):
        logger.debug("Starting to disable monitoring on seasons")

        updated_sonarr_object = filters.modify_sonarr_seasons(
            sonarr_object, seasons, False
        )

        try:
            logger.debug(f"Updating serie with Sonarr ID: {id}")
            self.sonarr_client.upd_series(updated_sonarr_object)
        except Exception as e:
            logger.error(e)
            logger.error(
                f"Something went wrong with updating the serie with ID: {id} in Sonarr, check the configuration or try --debug for more information"  # noqa: E501
            )

    def disable_monitored_episodes(self, id, episode_ids):
        logger.debug("Starting to disable monitoring on episodes")

        logger.debug(
            f"Updating episodes with IDs: {episode_ids} for serie with Sonarr ID: {id}"  # noqa: E501
        )

        try:

            self.sonarr_client.upd_episode_monitor(episode_ids, False)

        except Exception as e:
            logger.error(e)
            logger.error(
                f"Something went wrong with updating the episode with IDs: {episode_ids} in Sonarr, check the configuration or try --debug for more information"  # noqa: E501
            )

            return

        logger.debug(
            f"Updated episode with ID: {episode_ids} for serie with Sonarr ID: {id}"  # noqa: E501
        )

    def enable_monitored_serie(self, id, sonarr_object):
        logger.debug("Starting to enable monitoring on serie")

        sonarr_object["monitored"] = True

        try:
            logger.debug(f"Updating serie with Sonarr ID: {id}")
            self.sonarr_client.upd_series(sonarr_object)
        except Exception as e:
            logger.error(e)
            logger.error(
                f"Something went wrong with updating the serie with ID: {id} in Sonarr, check the configuration or try --debug for more information"  # noqa: E501
            )

    def enable_monitored_seasons(self, id, sonarr_object, seasons):
        logger.debug("Starting to enable monitoring on seasons")

        updated_sonarr_object = filters.modify_sonarr_seasons(
            sonarr_object, seasons, True
        )

        try:
            logger.debug(f"Updating serie with Sonarr ID: {id}")
            self.sonarr_client.upd_series(updated_sonarr_object)
        except Exception as e:
            logger.error(e)
            logger.error(
                f"Something went wrong with updating the serie with ID: {id} in Sonarr, check the configuration or try --debug for more information"  # noqa: E501
            )

    def enable_monitored_episodes(self, id, episode_ids):
        logger.debug("Starting to enable monitoring on episodes")

        logger.debug(
            f"Updating episodes with IDs: {episode_ids} for serie with Sonarr ID: {id}"  # noqa: E501
        )

        try:

            self.sonarr_client.upd_episode_monitor(episode_ids, True)

        except Exception as e:
            logger.error(e)
            logger.error(
                f"Something went wrong with updating the episode with IDs: {episode_ids} in Sonarr, check the configuration or try --debug for more information"  # noqa: E501
            )

            return

        logger.debug(
            f"Updated episode with ID: {episode_ids} for serie with Sonarr ID: {id}"  # noqa: E501
        )
