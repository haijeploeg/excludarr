from pathlib import Path
from pyarr import RadarrAPI, SonarrAPI
from pyarr.base import BaseArrAPI
from pyarr.exceptions import PyarrBadRequest
import typer
import sys

from typing import Dict, List, Optional
from loguru import logger

from . import __version__


from .utils.config import Config

# pyarr patches
from .utils import patch_pyarr

patch_pyarr.patch()

app = typer.Typer()


def get_and_add_tags(
    client: BaseArrAPI, tags: List[str], is_radarr: bool = True
) -> List[int]:
    # hacky way to implement a singleton :)
    if isinstance(client, RadarrAPI):
        if not hasattr(get_and_add_tags, "tags_on_radarr"):
            setattr(get_and_add_tags, "tags_on_radarr", {})
            result_tags = client.get_tag()
            for i in result_tags:
                get_and_add_tags.tags_on_radarr[i["label"]] = i["id"]  # type: ignore  # noqa: E501

        tags_on_radarr_or_sonarr = get_and_add_tags.tags_on_radarr  # type: ignore  # noqa: E501
    elif isinstance(client, SonarrAPI):
        if not hasattr(get_and_add_tags, "tags_on_sonarr"):
            setattr(get_and_add_tags, "tags_on_sonarr", {})
            result_tags = client.get_tag()
            for i in result_tags:
                get_and_add_tags.tags_on_sonarr[i["label"]] = i["id"]  # type: ignore  # noqa: E501

        tags_on_radarr_or_sonarr = get_and_add_tags.tags_on_sonarr  # type: ignore  # noqa: E501
    else:
        raise Exception("client is instance of a class that is not supported")

    tag_ids: List[int] = []

    for tag in tags:
        if tag in tags_on_radarr_or_sonarr.keys():
            tag_ids.append(tags_on_radarr_or_sonarr[tag])
            continue

        logger.info(f"Creating tag '{tag}'")

        new_tag = client.create_tag(tag)
        tags_on_radarr_or_sonarr[new_tag["label"]] = new_tag["id"]
        tag_ids.append(tags_on_radarr_or_sonarr[new_tag["label"]])

    return tag_ids


def add_movies(config: Config, ignore_unknown_tags: bool = True):

    if config.radarr_url is None:
        logger.error("No url for Radarr was provided, Skipping Radarr")
        return

    if config.radarr_api_key is None:
        logger.error("No API key for Radarr was provided, Skipping Radarr")
        return

    if config.radarr_movies is None:
        logger.error("Movie list for Radarr was empty")
        return

    radarr_client = RadarrAPI(config.radarr_url, config.radarr_api_key)

    # root_dir = radarr_client.get_root_folder()[0]["path"]  # type: ignore
    quality_profile_id = radarr_client.get_quality_profile()[0]["id"]

    logger.info(f"got movies: {config.radarr_movies}")
    for movie in config.radarr_movies:
        logger.info(f"{movie}")

        if "title" in movie:
            title = movie["title"]
        else:
            logger.info("skipping entry, no title")
            continue

        logger.info(f"Looking up {title}")
        movie_to_add = radarr_client.lookup_movie(term=title)[0]

        tag_labels_from_config: List[str] = movie.get("tags", [])

        tag_ids = get_and_add_tags(radarr_client, tag_labels_from_config)

        monitored: bool = movie.get("monitored", False)

        logger.info(f"Adding {title}")
        try:
            radarr_client.add_movie(
                movie=movie_to_add,
                root_dir="/movies",
                quality_profile_id=quality_profile_id,
                monitored=monitored,
                search_for_movie=False,
                tags=tag_ids,
            )
            logger.info(f"'{title}' added")

        except PyarrBadRequest:
            movie_to_update = radarr_client.get_movie(
                movie_to_add["tmdbId"], True
            )[
                0  # type: ignore
            ]  # type: ignore

            movie_to_update["monitored"] = monitored
            movie_to_update["tags"] = tag_ids

            radarr_client.upd_movie(movie_to_update)
            logger.info(f"'{title}' altready on Radarr, updated")

    logger.info("Done adding movies to Radarr")


def add_series(config: Config, ignore_unknown_tags: bool = True):

    if config.sonarr_url is None:
        logger.error("No url for Sonarr was provided, Skipping Sonarr")
        return

    if config.sonarr_api_key is None:
        logger.error("No API key for Sonarr was provided, Skipping Sonarr")
        return

    if config.sonarr_series is None:
        logger.error("Series list for Radarr was empty")
        return

    sonarr_client: SonarrAPI = SonarrAPI(
        config.sonarr_url, config.sonarr_api_key
    )

    # root_dir = radarr_client.get_root_folder()[0]["path"]  # type: ignore
    quality_profile_id = sonarr_client.get_quality_profile()[0]["id"]

    label_to_sonarr_id_mapping: dict[str, int] = {}

    logger.info(f"got series: {config.sonarr_series}")

    for serie in config.sonarr_series:
        logger.info(f"{serie}")

        if "title" in serie:
            title = serie["title"]
        else:
            logger.info("skipping entry, no title")
            continue

        logger.info(f"Looking up {title}")
        serie_to_add = sonarr_client.lookup_series(term=title)[0]

        tag_ids = get_and_add_tags(sonarr_client, serie.get("tags", []))

        monitored: bool = serie.get("monitored", False)

        logger.info(f"Adding {title}")
        try:
            added = sonarr_client.add_series(
                series=serie_to_add,
                root_dir="/tv",
                quality_profile_id=quality_profile_id,
                language_profile_id=None,
                monitored=False,
            )

            label_to_sonarr_id_mapping[title] = added["id"]
            logger.info(f"'{title}' added")

        except PyarrBadRequest:
            res = sonarr_client.get_series(serie_to_add["tvdbId"], True)[
                0  # type: ignore
            ]  # type: ignore

            label_to_sonarr_id_mapping[title] = res["id"]

            logger.info(f"'{title}' altready on Sonarr")

    # from time import sleep
    # sleep(3)

    from .utils.sonarr import sonarr_get_episode

    logger.info(
        "Done adding series to sonar, now update all of them for monitoring and tags"  # noqa: E501
    )
    for serie in config.sonarr_series:

        if "title" in serie:
            title = serie["title"]
        else:
            continue

        sonarr_id = label_to_sonarr_id_mapping[title]

        logger.info(f"updating {title} with id: {sonarr_id}")

        serie_to_update: Dict = sonarr_client.get_series(id_=sonarr_id)  # type: ignore   # noqa: E501

        # add tags
        tag_ids = get_and_add_tags(sonarr_client, serie.get("tags", []))
        serie_to_update["tags"] = tag_ids

        # set monitored for series
        monitored = serie.get("monitored", False)
        serie_to_update["monitored"] = monitored

        serie_to_update = sonarr_client.upd_series(serie_to_update)

        season_num_to_idx_map: Dict = {}
        for idx, s in enumerate(serie_to_update["seasons"]):
            season_num_to_idx_map[s["seasonNumber"]] = idx

        advanced: Dict = serie.get("advanced_monitored", {})

        seasons_to_skip_in_wildcard: List[int] = []
        should_process_wildcard = advanced.pop("*", None)

        seasons_in_config = [s for s in advanced.keys()]
        if should_process_wildcard is not None:
            for s_num, s_idx in season_num_to_idx_map.items():
                if str(s_num) in seasons_in_config:
                    continue

                advanced[str(s_num)] = should_process_wildcard

        for season_n, episodes in advanced.items():
            logger.info(f"updating {season_n} for {title}")

            try:
                season = int(season_n)
                if season not in season_num_to_idx_map.keys():
                    raise ValueError
            except ValueError:
                logger.info(
                    f"skipping {season_n} for {title}, reason: invalid season value"  # noqa: E501
                )
                continue

            should_add_season = True
            should_skip_add_episodes = False

            if isinstance(episodes, bool):
                should_skip_add_episodes = True
                should_add_season = episodes

            seasons_to_skip_in_wildcard.append(season)

            # update season
            serie_to_update["seasons"][season_num_to_idx_map[season]][
                "monitored"
            ] = should_add_season

            serie_to_update = sonarr_client.upd_series(serie_to_update)

            logger.info(f"{title} - updated season {season}")

            if should_skip_add_episodes:
                continue

            episodes_from_sonarr: List[Dict] = []

            episodes_from_sonarr = sonarr_get_episode(
                sonarr_client=sonarr_client,
                id_=sonarr_id,
                series=True,
                season=season,
            )

            episodes_to_set_monitored: List[int] = []
            episodes_to_set_unmonitored: List[int] = []

            for episode in episodes_from_sonarr:
                if should_add_season or (
                    not should_add_season
                    and episode["episodeNumber"] in episodes
                ):
                    episodes_to_set_monitored.append(episode["id"])
                else:
                    episodes_to_set_unmonitored.append(episode["id"])

            # update episodes
            sonarr_client.upd_episode_monitor(episodes_to_set_monitored, True)

            # update episodes
            sonarr_client.upd_episode_monitor(
                episodes_to_set_unmonitored, False
            )

            logger.info(
                f"{title} - updated episodes {episodes_to_set_monitored} from season {season}"  # noqa: E501
            )

        logger.info(f"updated {title}")

    logger.info("Done adding movies to Radarr")


@app.command()
def setup(
    config_path: Path = typer.Option(
        "./config.yml",
        "-c",
        "--config",
        metavar="CONFIG",
        help='The location of your config file e.g: "./config.yml"',
        exists=True,
        dir_okay=False,
    ),
):
    """
    Initializes the command. Reads the configuration.
    """
    logger.info("Got setup as subcommand")

    logger.info("Reading configuration file")
    config = Config(config_path)

    add_movies(config)
    add_series(config)


def version_callback(value: bool):
    if value:
        typer.echo(f"arr_setup: v{__version__}")
        raise typer.Exit()


def _setup_logging(info):
    """
    Setup the log formatter for Excludarr
    """

    log_level = "INFO"

    logger.remove()

    logger.add(
        sys.stdout,
        colorize=True,
        format="[{time:YYYY-MM-DD HH:mm:ss}] - <level>{message}</level>",
        level=log_level,
    )


@app.callback()
def main(
    info: bool = False,
    version: Optional[bool] = typer.Option(
        None, "--version", callback=version_callback
    ),
):
    # Setup the logger
    _setup_logging(False)

    # Logging
    logger.info(f"Starting arr_setup v{__version__}")


def cli():
    app(prog_name="arr_setup")


if __name__ == "__main__":
    cli()
