import typer
import sys

from typing import Optional
from loguru import logger

import excludarr.commands.radarr as radarr
import excludarr.commands.sonarr as sonarr
import excludarr.commands.providers as providers

from excludarr import __version__


app = typer.Typer()
app.add_typer(radarr.app, name="radarr", help="Manages movies in Radarr.")
app.add_typer(sonarr.app, name="sonarr", help="Manages TV shows and seasons in Sonarr.")
app.add_typer(
    providers.app, name="providers", help="List all the possible providers for your locale."
)


def version_callback(value: bool):
    if value:
        typer.echo(f"Excludarr: v{__version__}")
        raise typer.Exit()


def _setup_logging(debug):
    """
    Setup the log formatter for Excludarr
    """

    log_level = "INFO"
    if debug:
        log_level = "DEBUG"

    logger.remove()
    logger.add(
        sys.stdout,
        colorize=True,
        format="[{time:YYYY-MM-DD HH:mm:ss}] - <level>{message}</level>",
        level=log_level,
    )


@app.callback()
def main(
    debug: bool = False,
    version: Optional[bool] = typer.Option(None, "--version", callback=version_callback),
):
    """
    Keep your storage happy with Excludarr. This CLI tool will exclude
    and delete movies and series from Radarr and Sonarr if they are not 
    streaming on any of the configured streaming providers.
    """

    # Setup the logger
    _setup_logging(debug)

    # Logging
    logger.debug(f"Starting Excludarr v{__version__}")


def cli():
    app(prog_name="excludarr")


if __name__ == "__main__":
    cli()
