import datetime


def get_tmdb_ids(external_ids):
    try:
        tmdb_ids = [
            int(x["external_id"])
            for x in external_ids
            if x["provider"] == "tmdb_latest" or x["provider"] == "tmdb"
        ]
        tmdb_ids = list(set(tmdb_ids))
    except (KeyError, IndexError):
        tmdb_ids = []

    return tmdb_ids


def get_jw_providers(raw_providers, providers):
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


def get_jw_movie_providers(raw_movie_data):
    providers = {}

    try:
        for entry in raw_movie_data["offers"]:
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


def get_release_date(raw_movie_data):
    release_cinema = raw_movie_data.get("inCinemas")
    release_digital = raw_movie_data.get("digitalRelease")
    release_physical = raw_movie_data.get("physicalRelease")

    if release_cinema:
        release_date = datetime.datetime.strptime(release_cinema, "%Y-%m-%dT%H:%M:%SZ").strftime(
            "%Y-%m-%d"
        )
    elif release_digital:
        release_date = datetime.datetime.strptime(release_digital, "%Y-%m-%dT%H:%M:%SZ").strftime(
            "%Y-%m-%d"
        )
    elif release_physical:
        release_date = datetime.datetime.strptime(release_physical, "%Y-%m-%dT%H:%M:%SZ").strftime(
            "%Y-%m-%d"
        )
    else:
        release_date = "Unknown"

    return release_date


def get_filesize_gb(filesize):
    filesize_gb = filesize / 1024.0 ** 3
    return "%.2f" % filesize_gb + "GB"
