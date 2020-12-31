#!/usr/bin/env python

# Imports
import os

from pyradarr import Radarr
from pytmdb import TMDB, TMDBException

# TMDB settings
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "supersecret")
TMDB_LOCALE = os.getenv("TMDB_LOCALE", "NL")

# Radarr settings
RADARR_URL = os.getenv("RADARR_URL", "http://localhost:7878")
RADARR_API_KEY = os.getenv("RADARR_API_KEY", "supersecret")
RADARR_VERIFY_SSL = os.getenv("RADARR_VERIFY_SSL", True)
RADARR_REMOVE_IF_NOT_FOUND = os.getenv("RADARR_REMOVE_IF_NOT_FOUND", True)
RADARR_DELETE_FILES = os.getenv("RADARR_DELETE_FILES", True)
RADARR_ADD_IMPORT_EXCLUSION = os.getenv("RADARR_ADD_IMPORT_EXCLUSION", True)
RADARR_EXCLUDE_PROVIDERS = os.getenv("RADARR_EXCLUDE_PROVIDERS", "netflix").split(",")

# Initialize TMDB API
tmdb = TMDB(TMDB_API_KEY)

# Initialize Radarr API
radarr = Radarr(RADARR_URL, RADARR_API_KEY, ssl_verify=RADARR_VERIFY_SSL)

# Setup the needed lists
exclude_providers = [x.lower() for x in RADARR_EXCLUDE_PROVIDERS]
radarr_delete_ids = []

# Get all movies from radarr and check if tmdbid is in netflix list
for movie in radarr.movie.get_all_movies():
    try:
        # Try to lookup the movie on TMDB using the tmdbid retrieved from Radarr
        providers = tmdb.movie.get_watch_providers(movie["tmdbId"])
        local_providers = providers["results"][TMDB_LOCALE]
        try:
            # Try to check if the movie is being streamed in the selected country
            if (
                local_providers["flatrate"][0]["provider_name"].lower()
                in exclude_providers
            ):
                print("Will remove: {} - {}".format(movie["id"], movie["title"]))
                radarr_delete_ids.append(movie["id"])
        except KeyError:
            pass
    except TMDBException:
        # If the movie is not found on TMDB, mark it for deletion if requested by the user
        if RADARR_REMOVE_IF_NOT_FOUND:
            print("Will remove: {} - {}".format(movie["id"], movie["title"]))
            radarr_delete_ids.append(movie["id"])
    except KeyError:
        # This will only raise if there is no streaming provider found
        # using the selected country
        pass

# Delete the movies in a single API call
if radarr_delete_ids:
    radarr.movie.delete_movies(
        radarr_delete_ids,
        delete_files=RADARR_DELETE_FILES,
        add_import_exclusion=RADARR_ADD_IMPORT_EXCLUSION,
    )

print("Deleted {} movie(s)".format(len(radarr_delete_ids)))
