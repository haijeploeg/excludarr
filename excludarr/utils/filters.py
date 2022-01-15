import datetime
import itertools


def flatten(lst):
    return list(set(itertools.chain.from_iterable(lst)))


def bool2str(value):
    if value:
        return "Yes"
    else:
        return "No"


def get_tmdb_ids(external_ids):
    try:
        tmdb_ids = [
            int(x["external_id"])
            for x in external_ids
            if (x["provider"] == "tmdb_latest" or x["provider"] == "tmdb") and x["external_id"].isnumeric()
        ]
        tmdb_ids = list(set(tmdb_ids))
    except (KeyError, IndexError):
        tmdb_ids = []

    return tmdb_ids

def get_imdb_ids(external_ids):
    try:
        imdb_ids = [
            x["external_id"]
            for x in external_ids
            if x["provider"] == "imdb_latest" or x["provider"] == "imdb"
        ]
        imdb_ids = list(set(imdb_ids))
    except (KeyError, IndexError):
        imdb_ids = []

    return imdb_ids


def get_providers(raw_providers, providers):
    providers = [x.lower() for x in providers]
    jw_providers = {}

    for entry in raw_providers:
        if entry["clear_name"].lower() in providers:
            jw_providers.update(
                {
                    entry["id"]: {
                        "short_name": entry["short_name"],
                        "clear_name": entry["clear_name"],
                    }
                }
            )

    return jw_providers


def get_jw_providers(raw_data):
    providers = {}

    try:
        for entry in raw_data["offers"]:
            providers.update(
                {
                    entry["provider_id"]: {
                        "shortname": entry["package_short_name"],
                    }
                }
            )
    except KeyError:
        # This means that there are no providers found in the configured locale.
        # Ignore this exception and return an empty dict.
        pass

    return providers


def get_release_date(raw_movie_data, format="%Y-%m-%d"):
    release_cinema = raw_movie_data.get("inCinemas")
    release_digital = raw_movie_data.get("digitalRelease")
    release_physical = raw_movie_data.get("physicalRelease")

    if release_cinema:
        release_date = datetime.datetime.strptime(release_cinema, "%Y-%m-%dT%H:%M:%SZ").strftime(
            format
        )
    elif release_digital:
        release_date = datetime.datetime.strptime(release_digital, "%Y-%m-%dT%H:%M:%SZ").strftime(
            format
        )
    elif release_physical:
        release_date = datetime.datetime.strptime(release_physical, "%Y-%m-%dT%H:%M:%SZ").strftime(
            format
        )
    else:
        release_date = None

    return release_date


def get_filesize_gb(filesize):
    filesize_gb = filesize / 1024.0 ** 3
    return "%.2f" % filesize_gb + "GB"


def get_episode_data(episodes, season_number, episode_number):
    episode_data = {}

    for episode in episodes:
        if season_number == episode["seasonNumber"] and episode_number == episode["episodeNumber"]:
            episode_data = {
                "episode_id": episode["id"],
                "monitored": episode["monitored"],
                "has_file": episode.get("hasFile", False),
            }
            break

    return episode_data


def get_episode_file_id(episodes, season_number, episode_number):
    episode_file_ids = []

    for episode in episodes:
        if (
            season_number == episode["seasonNumber"]
            and episode_number == episode["episodeNumber"]
            and episode.get("hasFile", False)
        ):
            episode_file_ids.append(episode["episodeFileId"])

    return episode_file_ids


def get_pretty_seasons(seasons):
    season_data = []

    for season in seasons:
        season_number = season["season"]
        season_data.append(f"Season {season_number}")

    return ", ".join(season_data)


def get_pretty_episodes(episodes):
    episode_data = []

    for episode in episodes:
        season_number = episode["season"]
        episode_number = episode["episode"]
        episode_data.append(f"S{season_number:02d}E{episode_number:02d}")

    return ", ".join(episode_data)


def get_providers_from_seasons_episodes(seasons, episodes):
    season_providers = flatten(
        [season["providers"] for season in seasons if season.get("providers")]
    )
    episode_providers = flatten(
        [episode["providers"] for episode in episodes if episode.get("providers")]
    )

    providers = list(set(season_providers + episode_providers))

    return ", ".join(providers)


def modify_sonarr_seasons(sonarr_object, seasons, monitored):
    sonarr_seasons = sonarr_object["seasons"]

    for entry in sonarr_seasons:
        if entry["seasonNumber"] in seasons:
            entry["monitored"] = monitored

    sonarr_object["seasons"] = sonarr_seasons

    return sonarr_object
