#!/usr/bin/env python

# Imports
import os

from pyradarr import Radarr
from pytmdb import TMDB, TMDBException

# TMDB settings
TMDB_API_KEY = os.getenv('TMDB_API_KEY', 'supersecret')
LOCALE = 'NL'

# Radarr settings
RADARR_URL = os.getenv('RADARR_URL', 'http://localhost:7878')
RADARR_API_KEY = os.getenv('RADARR_API_KEY', 'supersecret')
RADARR_VERIFY_SSL = os.getenv('RADARR_VERIFY_SSL', True)
RADARR_REMOVE_IF_NOT_FOUND = True
RADARR_EXCLUDE_PROVIDERS = ['netflix']

# Initialize TMDB API
tmdb = TMDB(TMDB_API_KEY)

# Initialize Radarr API
radarr = Radarr(RADARR_URL, RADARR_API_KEY, ssl_verify=RADARR_VERIFY_SSL)

# Setup the needed lists
exclude_providers = [x.lower() for x in RADARR_EXCLUDE_PROVIDERS]
radarr_delete_ids = []

# Get all movies from radarr and check if tmdbid is in netflix list
for movie in radarr.movie.get():
    try:
        # Try to lookup the movie on TMDB using the tmdbid retrieved from Radarr
        providers = tmdb.movie.get_watch_providers(movie['tmdbId'])
        local_providers = providers['results'][LOCALE]
        try:
            # Try to check if the movie is being streamed in the selected country
            if local_providers['flatrate'][0]['provider_name'].lower() in exclude_providers:
                print('Will remove: {} - {}'.format(movie['id'], movie['title']))
                radarr_delete_ids.append(movie['id'])
        except KeyError:
            pass
    except TMDBException:
        # If the movie is not found on TMDB, mark it for deletion if requested by the user
        if RADARR_REMOVE_IF_NOT_FOUND:
            print('Will remove: {} - {}'.format(movie['id'], movie['title']))
            radarr_delete_ids.append(movie['id'])
    except KeyError:
        # This will only raise if there is no streaming provider found 
        # using the selected country
        pass

# Delete the movies in a single API call
if radarr_delete_ids:
    radarr.movie.delete(radarr_delete_ids, deleteFiles=True, addImportExclusion=True)

print('Deleted {} movie(s)'.format(len(radarr_delete_ids)))
