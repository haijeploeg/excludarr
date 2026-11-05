from typing import Collection, Dict, List
from pyarr.base import BaseArrAPI
from loguru import logger


def filter_entries(
    arr_client: BaseArrAPI,
    radarr_movies: Collection,
    bl_movies: Collection,
    bl_tags: Collection,
    monitored: None | bool = None,
) -> List:

    logger.debug("Getting tags from Radarr")

    all_tags: List = arr_client.get_tag()  # type: ignore

    logger.debug(f"Tags from Radarr:  {all_tags}")
    logger.debug(f"Tags to blacklist: {bl_tags}")

    bl_tag_ids = set([t["id"] for t in all_tags if t["label"] in bl_tags])

    logger.debug("blacklisting movies")

    def filter_fn(m: Dict) -> bool:
        return (
            # title must not be in blacklist
            m["title"] not in bl_movies
            # should not have any blacklisted tags
            and len(set(m["tags"]) & bl_tag_ids) == 0
            # check monitored status
            and (
                monitored is None
                or (monitored is not None and m["monitored"] == monitored)
            )
        )

    return list(filter(filter_fn, radarr_movies))
