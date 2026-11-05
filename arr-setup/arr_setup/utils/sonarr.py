from pyarr import SonarrAPI
from pyarr.types import JsonArray
from tenacity import retry, wait_fixed, stop_after_attempt, retry_if_result


def is_empty(value):
    """Return True if value is False"""
    return len(value) == 0


@retry(
    wait=wait_fixed(1),
    stop=stop_after_attempt(5),
    retry=retry_if_result(is_empty),
)
def sonarr_get_episode(
    sonarr_client: SonarrAPI,
    id_: int,
    series: bool = False,
    season: int | None = None,
) -> JsonArray:
    return sonarr_client.get_episode(id_=id_, series=True, season=season)
