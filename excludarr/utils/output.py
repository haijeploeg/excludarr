import rich

from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.prompt import Confirm
from rich.text import Text
from rich import box

import excludarr.utils.filters as filters

from excludarr.utils.enums import Action


def print_movies_to_exclude(movies, total_filesize):
    # Setup console
    console = Console()

    # Setup table
    table = Table(show_footer=True, row_styles=["none", "dim"], box=box.MINIMAL, pad_edge=False)
    with Live(table, console=console, screen=False):
        # Setup table columns and totals
        table.add_column("Release Date") or "Unknown"
        table.add_column("Title", Text.from_markup("[b][i]Total Used Diskspace", justify="right"))
        table.add_column("Used Diskspace", filters.get_filesize_gb(total_filesize))
        table.add_column("Streaming Providers")

        for _, movie in movies.items():
            release_date = movie["release_date"]
            title = movie["title"]
            diskspace = filters.get_filesize_gb(movie["filesize"])
            providers = ", ".join(movie["providers"])

            # Add table rows
            table.add_row(release_date, title, diskspace, providers)


def print_movies_to_re_add(movies):
    # Setup console
    console = Console()

    # Setup table
    table = Table(show_footer=False, row_styles=["none", "dim"], box=box.MINIMAL, pad_edge=False)
    with Live(table, console=console, screen=False):
        # Setup table columns
        table.add_column("Release Date")
        table.add_column("Title")

        for _, movie in movies.items():
            release_date = movie["release_date"]
            title = movie["title"]

            # Add table rows
            table.add_row(release_date, title)


def print_series_to_exclude(series, total_filesize):
    # Setup console
    console = Console()

    # Setup table
    table = Table(show_footer=True, row_styles=["none", "dim"], box=box.MINIMAL, pad_edge=False)
    with Live(table, console=console, screen=False):
        # Setup table columns and totals
        table.add_column("Release Year")
        table.add_column("Title", Text.from_markup("[b][i]Total Used Diskspace", justify="right"))
        table.add_column("Used Diskspace", filters.get_filesize_gb(total_filesize))
        table.add_column("Seasons")
        table.add_column("Episodes")
        table.add_column("Providers")
        table.add_column("Ended")
        table.add_column("Full delete")

        for _, serie in series.items():
            release_year = str(serie["release_year"])
            title = serie["title"]
            diskspace = filters.get_filesize_gb(serie["filesize"])
            season = filters.get_pretty_seasons(serie["seasons"])
            episodes = filters.get_pretty_episodes(serie["episodes"])
            providers = serie["providers"]
            ended = filters.bool2str(serie["ended"])
            full_delete = filters.bool2str(serie["full_delete"])

            # Add table rows
            table.add_row(
                release_year, title, diskspace, season, episodes, providers, ended, full_delete
            )


def print_series_to_re_add(series):
    # Setup console
    console = Console()

    # Setup table
    table = Table(show_footer=False, row_styles=["none", "dim"], box=box.MINIMAL, pad_edge=False)
    with Live(table, console=console, screen=False):
        # Setup table columns
        table.add_column("Release Year")
        table.add_column("Title")
        table.add_column("Seasons")
        table.add_column("Episodes")
        table.add_column("Ended")

        for _, serie in series.items():
            release_year = str(serie["release_year"])
            title = serie["title"]
            season = filters.get_pretty_seasons(serie["seasons"])
            episodes = filters.get_pretty_episodes(serie["episodes"])
            ended = filters.bool2str(serie["ended"])

            # Add table rows
            table.add_row(release_year, title, season, episodes, ended)


def print_providers(providers):
    # Setup console
    console = Console()

    # Setup table
    table = Table(show_footer=False, row_styles=["none", "dim"], box=box.MINIMAL, pad_edge=False)
    with Live(table, console=console, screen=False):
        # Setup table columns
        table.add_column("JustWatch ID")
        table.add_column("Provider")

        for provider in providers:
            id = str(provider["id"])
            clear_name = provider["clear_name"]

            # Add table rows
            table.add_row(id, clear_name)


def ask_confirmation(action, kind):
    if action == Action.delete:
        confirmation = Confirm.ask(
            f"Are you sure you want to delete the listed {kind}?", default=False
        )
    elif action == Action.not_monitored:
        confirmation = Confirm.ask(
            f"Are you sure you want to change the listed {kind} to not-monitored?", default=False
        )
    elif action == "re-add":
        confirmation = Confirm.ask(
            f"Are you sure you want to re monitor the listed {kind}?", default=False
        )

    return confirmation


def print_success_exclude(action, kind):
    if action == Action.delete and kind == "series":
        rich.print(
            "Succesfully deleted the series and/or changed the status of serveral seasons and episodes listed in Sonarr to not monitored!"
        )
    elif action == Action.delete and kind == "movies":
        rich.print("Succesfully deleted the movies from Radarr!")
    elif action == Action.not_monitored and kind == "series":
        rich.print(
            "Succesfully changed the status of the series and/or several seasons and episodes listed in Sonarr to not monitored!"
        )
    elif action == Action.not_monitored and kind == "movies":
        rich.print(
            "Succesfully changed the status of the movies listed in Radarr to not monitored!"
        )
