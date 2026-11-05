from typing import Optional
from pyarr import RadarrAPI, SonarrAPI
from pyarr.types import JsonObject, JsonArray


# GET /episode
def __sonarr_get_episode(
    self, id_: int, series: bool = False, season: int | None = None
) -> JsonObject:
    """Get episodes by ID or series

    Args:
        id_ (int): ID for Episode or Series.
        series (bool, optional): Set to true if the ID is for a Series. Defaults to false.

    Returns:
        JsonArray: List of dictionaries with items
    """  # noqa: E501
    params = {"seriesId": id_}
    if season is not None:
        params["seasonNumber"] = season

    return self._get(
        f"episode{'' if series else f'/{id_}'}",
        self.ver_uri,
        params=params if series else None,
    )


# PUT /season/monitor
def __sonarr_upd_season_monitor(
    self, season_ids: list[int], monitored: bool = True
) -> JsonArray:
    """Update episode monitored status

    Args:
        episode_ids (list[int]): All episode IDs to be updated
        monitored (bool, optional): True or False. Defaults to True.

    Returns:
        JsonArray: list of dictionaries containing updated records
    """
    return self._put(
        "season/monitor",
        self.ver_uri,
        data={"seasonIds": season_ids, "monitored": monitored},
    )


def __upd_movie(
    self,
    data: JsonObject,
    move_files: Optional[bool] = None,
) -> JsonObject:
    """Updates a movie in the database.

    Args:
        data (JsonObject): Dictionary containing an object obtained from get_movie()
        move_files (Optional[bool], optional): Have radarr move files when updating. Defaults to None.

    Returns:
        JsonObject: Dictionary with updated record
    """  # noqa: E501
    params = {}
    if move_files is not None:
        params["moveFiles"] = move_files
    return self._put(
        "movie",
        self.ver_uri,
        data=data,
        params=params,
    )


def patch():
    # for some reason `add_series` does not accept `tags` when adding a serie
    # even if the API supports it
    setattr(SonarrAPI, "get_episode", __sonarr_get_episode)
    setattr(SonarrAPI, "upd_season_monitor", __sonarr_upd_season_monitor)

    # there was a random print inside this function, now there is not :)
    setattr(RadarrAPI, "upd_movie", __upd_movie)
