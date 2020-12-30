#!/usr/bin/env python

class RadarrException(Exception):

    def __init__(self, error_code, error_message):
        Exception.__init__(self, error_message)
        self.error_code = error_code
        self.error_message = error_message

    def __str__(self):
        return '[{}] - {}'.format(self.error_code, self.error_message)


class RadarrTooManyVariablesException(Exception):
    pass


class RadarrInvalidIdSupplied(Exception):
    pass


class RadarrInvalidApiKey(Exception):
    pass


class RadarrMovieNotFound(Exception):
    pass


class RadarrValidationException(Exception):
    pass