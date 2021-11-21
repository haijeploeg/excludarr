def get_tmdb_id(external_ids):
    try:
        tmdb_id = [
            x["external_id"] for x in external_ids if x["provider"] == "tmdb_latest"
        ][0]
        tmdb_id = int(tmdb_id)
    except (KeyError, IndexError):
        tmdb_id = None

    return tmdb_id


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
