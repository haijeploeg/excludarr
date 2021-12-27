import rich
import typer

from typing import List, Optional
from loguru import logger

import excludarr.utils.output as output

from excludarr.core.sonarr_actions import SonarrActions
from excludarr.utils.config import Config
from excludarr.utils.enums import Action

app = typer.Typer()


@app.command(help="Exclude TV shows in Sonarr by deleting or not monitoring them")
def exclude(
    providers: Optional[List[str]] = typer.Option(
        None,
        "-p",
        "--provider",
        metavar="PROVIDER",
        help="Override the configured streaming providers.",
    ),
    locale: Optional[str] = typer.Option(
        None, "-l", "--locale", metavar="LOCALE", help="Your locale e.g: en_US."
    ),
    action: Action = typer.Option(..., "-a", "--action", help="Change the status in Radarr."),
    delete_files: bool = typer.Option(
        False, "-d", "--delete-files", help="Delete already downloaded files."
    ),
    exclusion: bool = typer.Option(
        False, "-e", "--exclusion", help="Add an exclusion to prevent auto importing."
    ),
    yes: bool = typer.Option(False, "-y", "--yes", help="Auto accept the confirmation notice."),
    progress: bool = typer.Option(
        False, "--progress", help="Track the progress using a progressbar."
    ),
):
    # Debug logging
    logger.debug("Got exclude as subcommand")
    logger.debug(f"Got CLI values for -p, --provider option: {', '.join(providers)}")
    logger.debug(f"Got CLI values for -l, --locale option: {locale}")
    logger.debug(f"Got CLI values for -a, --action option: {action}")
    logger.debug(f"Got CLI values for -d, --delete option: {delete_files}")
    logger.debug(f"Got CLI values for -e, --exclusion option: {exclusion}")
    logger.debug(f"Got CLI values for -y, --yes option: {yes}")
    logger.debug(f"Got CLI values for --progress option: {progress}")

    # Disable the progress bar when debug logging is active
    if loglevel == 10:
        disable_progress = True
    elif progress and loglevel != 10:
        disable_progress = False
    else:
        disable_progress = True

    # Determine if CLI options should overwrite configuration settings
    if not providers:
        providers = config.providers
    if not locale:
        locale = config.locale

    # Setup Sonarr Actions to control the different tasks
    sonarr = SonarrActions(
        config.sonarr_url, config.sonarr_api_key, locale, config.sonarr_verify_ssl
    )

    series_to_exclude = sonarr.get_series_to_exclude(
        providers, config.fast_search, disable_progress, tmdb_api_key=config.tmdb_api_key
    )

    # Only take monitored seasons and episodes in encounter
    for sonarr_id, values in series_to_exclude.items():
        if delete_files:
            values["episodes"] = [
                episode
                for episode in values["episodes"]
                if episode.get("monitored", False) or episode.get("has_file", False)
            ]
            values["seasons"] = [
                season
                for season in values["seasons"]
                if season.get("monitored", False) or season.get("has_file", False)
            ]
        else:
            values["episodes"] = [
                episode for episode in values["episodes"] if episode.get("monitored", False)
            ]
            values["seasons"] = [
                season for season in values["seasons"] if season.get("monitored", False)
            ]

        # Determine if serie should be deleted fully
        sonarr_total_monitored_seasons = len(
            [
                season
                for season in values["sonarr_object"]["seasons"]
                if season.get("monitored", False)
            ]
        )
        total_seasons = len([season["season"] for season in values["seasons"]])

        if (
            total_seasons == sonarr_total_monitored_seasons
            and values["ended"]
            and action == Action.delete
        ):
            values["full_delete"] = True
        else:
            values["full_delete"] = False

    if action == Action.not_monitored:
        series_to_exclude = {
            id: values
            for id, values in series_to_exclude.items()
            if (values["episodes"] or values["seasons"])
            and values["title"] not in config.sonarr_excludes
        }
    else:
        series_to_exclude = {
            id: values
            for id, values in series_to_exclude.items()
            if (values["episodes"] or values["seasons"])
            or values["full_delete"]
            and values["title"] not in config.sonarr_excludes
        }

    # Create a list of the Sonarr IDs
    series_to_exclude_ids = list(series_to_exclude.keys())

    # If there are series to exclude
    if series_to_exclude_ids:
        # Calculate total filesize
        total_filesize = sum([serie["filesize"] for _, serie in series_to_exclude.items()])

        # Print the serie in table format
        output.print_series_to_exclude(series_to_exclude, total_filesize)

        # Check for confirmation
        if not yes:
            confirmation = output.ask_confirmation(action, "series")
            if not confirmation:
                logger.warning("Aborting Excludarr because user did not confirm the question")
                raise typer.Abort()
        else:
            confirmation = True

        if confirmation:
            for sonarr_id, data in series_to_exclude.items():
                sonarr_object = data["sonarr_object"]
                sonarr_total_seasons = sonarr_object["statistics"]["seasonCount"]
                sonarr_full_delete = data["full_delete"]
                seasons = [season["season"] for season in data["seasons"]]
                episodes = data["episodes"]
                episode_ids = [
                    episode["episode_id"]
                    for episode in episodes
                    if episode.get("episode_id", False)
                ]
                episode_files = data["sonarr_file_ids"]

                # Check if total seasons match with the amount of seasons to exclude and delete or
                # change the status to not monitored for the whole serie
                if sonarr_full_delete:
                    if action == Action.delete:
                        sonarr.delete_serie(sonarr_id, delete_files, exclusion)
                    elif action == Action.not_monitored:
                        sonarr.disable_monitored_serie(sonarr_id, sonarr_object)
                        sonarr.disable_monitored_seasons(
                            sonarr_id, sonarr_object, list(range(sonarr_total_seasons + 1))
                        )

                        # Delete the episode files if delete flag is set
                        if delete_files and episode_files:
                            sonarr.delete_episode_files(sonarr_id, episode_files)
                else:
                    # Set the seasons and episodes to not-monitored
                    if seasons:
                        sonarr.disable_monitored_seasons(sonarr_id, sonarr_object, seasons)
                    if episodes:
                        sonarr.disable_monitored_episodes(sonarr_id, episode_ids)

                    # Delete the episode files if delete flag is set
                    if delete_files and episode_files:
                        sonarr.delete_episode_files(sonarr_id, episode_files)

            output.print_success_exclude(action, "series")
    else:
        rich.print("There are no more series also available on the configured streaming providers!")


@app.command(help="Change status of series to monitored if no provider is found")
def re_add(
    providers: Optional[List[str]] = typer.Option(
        None,
        "-p",
        "--provider",
        metavar="PROVIDER",
        help="Override the configured streaming providers.",
    ),
    locale: Optional[str] = typer.Option(
        None, "-l", "--locale", metavar="LOCALE", help="Your locale e.g: en_US."
    ),
    yes: bool = typer.Option(False, "-y", "--yes", help="Auto accept the confirmation notice."),
    progress: bool = typer.Option(
        False, "--progress", help="Track the progress using a progressbar."
    ),
):
    # Debug logging
    logger.debug("Got exclude as subcommand")
    logger.debug(f"Got CLI values for -p, --provider option: {', '.join(providers)}")
    logger.debug(f"Got CLI values for -l, --locale option: {locale}")
    logger.debug(f"Got CLI values for -y, --yes option: {yes}")
    logger.debug(f"Got CLI values for --progress option: {progress}")

    # Disable the progress bar when debug logging is active
    if loglevel == 10:
        disable_progress = True
    elif progress and loglevel != 10:
        disable_progress = False
    else:
        disable_progress = True

    # Determine if CLI options should overwrite configuration settings
    if not providers:
        providers = config.providers
    if not locale:
        locale = config.locale

    # Setup Sonarr Actions to control the different tasks
    sonarr = SonarrActions(
        config.sonarr_url, config.sonarr_api_key, locale, config.sonarr_verify_ssl
    )

    series_to_re_add = sonarr.get_series_to_re_add(
        providers, config.fast_search, disable_progress, tmdb_api_key=config.tmdb_api_key
    )

    # Only take not monitored seasons and episodes in encounter
    for _, values in series_to_re_add.items():
        values["episodes"] = [
            episode for episode in values["episodes"] if not episode.get("monitored", True)
        ]
        values["seasons"] = [
            season for season in values["seasons"] if not season.get("monitored", True)
        ]

    series_to_re_add = {
        id: values
        for id, values in series_to_re_add.items()
        if (values["episodes"] or values["seasons"] or not values["sonarr_object"]["monitored"])
        and values["title"] not in config.sonarr_excludes
    }

    # Create a list of the Sonarr IDs
    series_to_re_add_ids = list(series_to_re_add.keys())

    # If there are series to exclude
    if series_to_re_add_ids:
        # Print the series in table format
        output.print_series_to_re_add(series_to_re_add)

        # Check for confirmation
        if not yes:
            confirmation = output.ask_confirmation("re-add", "series")
            if not confirmation:
                logger.warning("Aborting Excludarr because user did not confirm the question")
                raise typer.Abort()
        else:
            confirmation = True

        if confirmation:
            for sonarr_id, data in series_to_re_add.items():
                sonarr_object = data["sonarr_object"]
                sonarr_total_seasons = sonarr_object["statistics"]["seasonCount"]
                sonarr_total_not_monitored_seasons = len(
                    [season for season in sonarr_object["seasons"] if not season["monitored"]]
                )
                seasons = [season["season"] for season in data["seasons"]]
                total_seasons = len(seasons)
                episodes = data["episodes"]
                episode_ids = [
                    episode["episode_id"]
                    for episode in episodes
                    if episode.get("episode_id", False)
                ]
                all_episode_ids = data["all_episode_ids"]

                # Check if total seasons match with the amount of seasons to re-add and
                # change the status to monitored for the whole serie, seasons and episodes
                if (
                    sonarr_total_not_monitored_seasons == total_seasons
                    and sonarr_total_not_monitored_seasons != 0
                ):
                    sonarr.enable_monitored_serie(sonarr_id, sonarr_object)
                    sonarr.enable_monitored_seasons(
                        sonarr_id, sonarr_object, list(range(sonarr_total_seasons + 1))
                    )
                    sonarr.enable_monitored_episodes(sonarr_id, all_episode_ids)

                else:
                    # Enable monitoring on the serie object it self
                    sonarr.enable_monitored_serie(sonarr_id, sonarr_object)
                    # Set the seasons and episodes to monitored
                    if seasons:
                        sonarr.enable_monitored_seasons(sonarr_id, sonarr_object, seasons)
                    if episodes:
                        sonarr.enable_monitored_episodes(sonarr_id, episode_ids)

            rich.print(
                "Succesfully changed the status of the series listed in Sonarr to monitored!"
            )
    else:
        rich.print("There are no more series to re-add!")


@app.callback()
def init():
    """
    Initializes the command. Reads the configuration.
    """
    logger.debug("Got sonarr as subcommand")

    # Set globals
    global config
    global loglevel

    # Hacky way to get the current log level context
    loglevel = logger._core.min_level

    logger.debug("Reading configuration file")
    config = Config()


if __name__ == "__main__":
    app()
