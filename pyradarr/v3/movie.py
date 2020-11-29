#!/usr/bin/env python

from pyradarr.base import Manager
from pyradarr.exceptions import RadarrTooManyVariablesException

class Movie(Manager):
    
    def get(self, id=None, tmdb_id=None):
        # Check if id and tmdb_id are defined at the same time
        if id and tmdb_id:
            raise RadarrTooManyVariablesException('`id` and `tmdb_id` cannot be defined in a single call. Please choose either `id` or `tmdb_id`.')

        # Determine the path to use
        path = '/movie'
        if id:
            path = '/movie/{}'.format(id)

        # Determine the params
        params = None
        if tmdb_id:
            params = {'tmdbid': tmdb_id}

        # Excecute the API call
        return self.client.http_get(path, params=params)

    def delete(self, id, deleteFiles=False, addImportExclusion=False):
        # Define paths and params for a single deletion
        path = '/movie/{}'.format(id)
        params = {'deleteFiles': deleteFiles, 'addImportExclusion': addImportExclusion}
        
        # If id contains a list, create the appropiate data
        if isinstance(id, list):
            path = '/movie/editor'
            params = None
            json = {
                'movieIds': id, 
                'deleteFiles': deleteFiles, 
                'addImportExclusion': addImportExclusion
            }
        
        # Execute the API call
        return self.client.http_delete(path, json=json, params=params)