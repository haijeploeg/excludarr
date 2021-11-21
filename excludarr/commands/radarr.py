from typing import List, Optional

import typer
from core.radarr_actions import RadarrActions
from loguru import logger
from utils.config import Config
from utils.enums import Action

app = typer.Typer()


@app.command()
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
    action: Action = typer.Option(
        ..., "-a", "--action", help="Change the status in Radarr."
    ),
    remove_not_found: bool = typer.Option(
        False,
        "-r",
        "--remove-not-found",
        help="Exclude from Radarr if not found upstream.",
    ),
    delete_files: bool = typer.Option(
        False, "-d", "--delete", help="Delete already downloaded files."
    ),
    exclusion: bool = typer.Option(
        False, "-e", "--exclusion", help="Add an exclusion to prevent auto importing."
    ),
    yes: bool = typer.Option(
        False, "-y", "--yes", help="Auto accept the confirmation notice."
    ),
):
    # Debug logging
    logger.debug("Got exclude as subcommand")
    logger.debug(f"Got CLI values for -p, --provider option: {', '.join(providers)}")
    logger.debug(f"Got CLI values for -l, --locale option: {locale}")
    logger.debug(f"Got CLI values for -a, --action option: {action}")
    logger.debug(
        f"Got CLI values for -r, --remove-not-found option: {remove_not_found}"
    )
    logger.debug(f"Got CLI values for -d, --delete option: {delete_files}")
    logger.debug(f"Got CLI values for -e, --exclusion option: {exclusion}")
    logger.debug(f"Got CLI values for -y, --yes option: {yes}")

    # Determine if CLI options should overwrite configuration settings
    if not providers:
        providers = config.providers
    if not locale:
        locale = config.locale

    radarr = RadarrActions(
        config.radarr_url, config.radarr_api_key, locale, config.radarr_verify_ssl
    )
    movies_to_exclude = radarr.get_movies_to_exclude(providers)

    # TODO: if bulk delete fails, automatically fall back on legacy delete (delete one by one)


@app.command()
def check(user_name: str):
    typer.echo(f"Deleting user: {user_name}")


@app.callback()
def init():
    """
    Initializes the command. Reads the configuration and initializes the API.
    """
    logger.debug("Got Radarr as subcommand")

    # Set global config variable, so it can be used in other functions.
    global config

    config = Config()


if __name__ == "__main__":
    app()
