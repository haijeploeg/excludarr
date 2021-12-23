import copy

from io import IOBase
from yaml import dump, safe_load
from loguru import logger
from pathlib import Path

from excludarr.utils.redact import redact_config_dict


class Config:
    def __init__(self):
        self.__class__ = Config
        self.config = None

        possible_locations = (
            "/etc/excludarr/excludarr.yml",
            f"{Path.home()}/.config/excludarr/excludarr.yml",
            f"{Path.home()}/.excludarr/config/excludarr.yml",
            f"{Path.home()}/.excludarr.yml",
            "./.excludarr.yml",
        )

        config_file = self.determine_location(possible_locations)

        if config_file is not None:
            self.load(config_file)

    def determine_location(self, possible_locations):
        logger.debug("Determining which configfile to use")

        config_file = None
        for location in possible_locations:
            path = Path(location)

            if path.is_file():
                config_file = location

        logger.debug(f"Configfile to use: {config_file}")

        return config_file

    def load(self, config_file):
        logger.debug(f"Reading configfile: {config_file}")

        if isinstance(config_file, IOBase):
            self.config = safe_load(config_file)
        else:
            with open(config_file, "r") as _file:
                self.config = safe_load(_file)

        logger.debug(
            f"Read the following configuration: {redact_config_dict(copy.deepcopy(self.config))}"
        )

    def dump(self):
        return dump(self.config)

    @property
    def general_section(self):
        return self.config.get("general", {})

    @property
    def tmdb_section(self):
        return self.config.get("tmdb", {})

    @property
    def radarr_section(self):
        return self.config.get("radarr", {})

    @property
    def sonarr_section(self):
        return self.config.get("sonarr", {})

    @property
    def locale(self):
        return self.general_section.get("locale", None)

    @property
    def providers(self):
        return self.general_section.get("providers", [])

    @property
    def fast_search(self):
        return self.general_section.get("fast_search", True)

    @property
    def tmdb_api_key(self):
        return self.tmdb_section.get("api_key", None)

    @property
    def radarr_url(self):
        return self.radarr_section.get("url", None)

    @property
    def radarr_api_key(self):
        return self.radarr_section.get("api_key", None)

    @property
    def radarr_verify_ssl(self):
        return self.radarr_section.get("verify_ssl", False)

    @property
    def radarr_excludes(self):
        return self.radarr_section.get("exclude", [])

    @property
    def sonarr_url(self):
        return self.sonarr_section.get("url", None)

    @property
    def sonarr_api_key(self):
        return self.sonarr_section.get("api_key", None)

    @property
    def sonarr_verify_ssl(self):
        return self.sonarr_section.get("verify_ssl", False)

    @property
    def sonarr_excludes(self):
        return self.sonarr_section.get("exclude", [])
