import rich
import typer

from typing import List, Optional
from loguru import logger

import excludarr.utils.output as output

from excludarr.core.radarr_actions import RadarrActions
from excludarr.utils.config import Config
from excludarr.utils.enums import Action

app = typer.Typer()


@app.command(help="Exclude movies in Radarr by deleting or not monitoring them")
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
    """
    Radarr exclude function. This function handles the CLI input and determines which
    action (delete/not-monitored) should be executed. The function gathers all information
    from Radarr and checks if there is a match with the JustWatch API. Based on the results a
    table is printed and the user is asked for confirmation. Based on the CLI options the
    files in Radarr are also deleted.

    :param providers: A list of providers that should overwrite the configuration settings
    :param locale: The locale in en_US or two letter country code US
    :param action: The action that should be executed, either delete or not-monitored
    :param delete_files: Also delete the already downloaded movie files
    :param exclusion: Add import exclusion to prevent auto importing the movie again
    :param yes: Skip the confirmation notice and continue without user input
    :param progress: Show a progress bar, only works when no --debug flag is set
    :return: None
    """
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

    # Setup Radarr Actions to control the different tasks
    radarr = RadarrActions(
        config.radarr_url, config.radarr_api_key, locale, config.radarr_verify_ssl
    )

    # Get the movies to exclude and exclude the movies that are in the exclude list
    movies_to_exclude = radarr.get_movies_to_exclude(
        providers, config.fast_search, disable_progress
    )

    # Only take monitored movies when the action is not-monitored
    if action == Action.not_monitored:
        movies_to_exclude = {
            id: values
            for id, values in movies_to_exclude.items()
            if values["title"] not in config.radarr_excludes
            and values["radarr_object"]["monitored"]
        }
    else:
        movies_to_exclude = {
            id: values
            for id, values in movies_to_exclude.items()
            if values["title"] not in config.radarr_excludes
        }

    # Create a list of the Radarr IDs
    movies_to_exclude_ids = list(movies_to_exclude.keys())

    # If there are movies to exclude
    if movies_to_exclude_ids:
        # Calculate total filesize
        total_filesize = sum([movie["filesize"] for _, movie in movies_to_exclude.items()])

        # Print the movies in table format
        output.print_movies_to_exclude(movies_to_exclude, total_filesize)

        # Check for confirmation
        if not yes:
            confirmation = output.ask_confirmation(action, "movies")
            if not confirmation:
                logger.warning("Aborting Excludarr because user did not confirm the question")
                raise typer.Abort()
        else:
            confirmation = True

        if confirmation:
            # Determine and execute the action supplied (delete, not-monitored)
            if action == Action.delete:
                radarr.delete(movies_to_exclude_ids, delete_files, exclusion)
            elif action == Action.not_monitored:
                movie_info = [movie["radarr_object"] for _, movie in movies_to_exclude.items()]
                radarr.disable_monitored(movie_info)

                if delete_files:
                    radarr.delete_files(movies_to_exclude_ids)

            output.print_success_exclude(action, "movies")
    else:
        rich.print("There are no more movies also available on the configured streaming providers!")


@app.command(help="Change status of movies to monitored if no provider is found")
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
    logger.debug("Got re-add as subcommand")
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

    # Setup Radarr Actions to control the different tasks
    radarr = RadarrActions(
        config.radarr_url, config.radarr_api_key, locale, config.radarr_verify_ssl
    )

    # Get the movies that should be re monitored
    movies_to_re_add = radarr.get_movies_to_re_add(providers, config.fast_search, disable_progress)
    movies_to_re_add = {
        id: values
        for id, values in movies_to_re_add.items()
        if values["title"] not in config.radarr_excludes
    }

    # Create a list of the Radarr IDs
    movies_to_re_add_ids = list(movies_to_re_add.keys())

    # If there are movies to exclude
    if movies_to_re_add_ids:
        # Print the movies in table format
        output.print_movies_to_re_add(movies_to_re_add)

        # Check for confirmation
        if not yes:
            confirmation = output.ask_confirmation("re-add", "movies")
            if not confirmation:
                logger.warning("Aborting Excludarr because user did not confirm the question")
                raise typer.Abort()
        else:
            confirmation = True

        if confirmation:
            # Re-add the movies
            movie_info = [movie["radarr_object"] for _, movie in movies_to_re_add.items()]
            radarr.enable_monitored(movie_info)

            rich.print(
                "Succesfully changed the status of the movies listed in Radarr to monitored!"
            )

    else:
        rich.print("There are no more movies to re-add!")


@app.callback()
def init():
    """
    Initializes the command. Reads the configuration.
    """
    logger.debug("Got radarr as subcommand")

    # Set globals
    global config
    global loglevel

    # Hacky way to get the current log level context
    loglevel = logger._core.min_level

    logger.debug("Reading configuration file")
    config = Config()


if __name__ == "__main__":
    app()
