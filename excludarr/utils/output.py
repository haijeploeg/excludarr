from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.prompt import Confirm
from rich.text import Text
from rich import box

import utils.filters as filters
from utils.enums import Action


def print_movies_to_exclude(movies, total_filesize):
    # Setup console
    console = Console()

    # Setup table
    table = Table(show_footer=True, row_styles=["none", "dim"], box=box.MINIMAL, pad_edge=False)
    with Live(table, console=console, screen=False):
        # Setup table columns and totals
        table.add_column("Release Date")
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
        # Setup table columns and totals
        table.add_column("Release Date")
        table.add_column("Title")

        for _, movie in movies.items():
            release_date = movie["release_date"]
            title = movie["title"]

            # Add table rows
            table.add_row(release_date, title)


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
