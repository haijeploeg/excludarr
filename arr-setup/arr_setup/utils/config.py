import copy
from io import IOBase
from typing import Dict, List
from yaml import dump, safe_load
from loguru import logger
from pathlib import Path


# from excludarr
def redact_config_dict(data):
    """
    This function redacts secret values in the configuration dict.
    This prevents that logging prints plain api keys.
    """
    for key, value in data.items():
        # Redact the secret values
        if key == "api_key" and data[key]:
            data[key] = "<REDACTED>"

        # Check if there are still more dicts to loop over
        if isinstance(value, dict):
            redact_config_dict(value)

    return data


class NoConfigException(Exception):
    pass


class Config:
    _config: Dict

    def __init__(self, path: Path | None = None):
        self.__class__ = Config
        self._config = {}

        if path is not None:
            config_path = path
        else:
            config_path = Path("./config.yml")

        if not config_path.exists() or not config_path.is_file():
            raise NoConfigException("no valid config file was provided")

        self.load(config_path)

    def load(self, config_path: Path):
        logger.debug(f"Reading configfile: {config_path}")

        if isinstance(config_path, IOBase):
            self._config = safe_load(config_path)
        else:
            with open(config_path, "r") as _file:
                self._config = safe_load(_file)

        logger.info(
            f"Read the following configuration: {redact_config_dict(copy.deepcopy(self._config))}"  # noqa: E501
        )

    def dump(self):
        return dump(self._config)

    # root level
    @property
    def radarr_section(self) -> Dict:
        return self._config.get("radarr", {})

    @property
    def sonarr_section(self) -> Dict:
        return self._config.get("sonarr", {})

    # radarr level
    @property
    def radarr_url(self) -> str | None:
        return self.radarr_section.get("url", None)

    @property
    def radarr_api_key(self) -> str | None:
        return self.radarr_section.get("api_key", None)

    @property
    def radarr_verify_ssl(self) -> bool:
        return self.radarr_section.get("verify_ssl", False)

    @property
    def radarr_movies(self) -> List[Dict] | None:
        return self.radarr_section.get("movies", None)

    # sonarr level
    @property
    def sonarr_url(self) -> str | None:
        return self.sonarr_section.get("url", None)

    @property
    def sonarr_api_key(self) -> str | None:
        return self.sonarr_section.get("api_key", None)

    @property
    def sonarr_verify_ssl(self) -> bool:
        return self.sonarr_section.get("verify_ssl", False)

    @property
    def sonarr_series(self) -> List[Dict] | None:
        return self.sonarr_section.get("series", None)
