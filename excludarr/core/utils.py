def get_movie_providers(tmdb, tmdbid, country):
    # Get the providers in the specified country of the movie from TMDB
    tmdb_providers = tmdb.movie.get_watch_providers(tmdbid)["results"][country]

    # Add all found providers to a list
    providers = [x["provider_name"].lower() for x in tmdb_providers["flatrate"]]

    return providers
