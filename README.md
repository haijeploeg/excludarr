# Exclude Streaming Services from Radarr
By default there is no option to exclude streaming providers from the automatically imported movies throught lists in Radarr. I have created 2 basic API wrappers to connect to Radarr and TMDB (the available API wrappers did not work). This script will do the following:
1. Get a full overview of movies.
2. Exctract the tmdbid value of each movie found.
3. Lookup the extracted `tmdbid` value from Radarr at TMDB itself and check if the movie is available on one of the chosen providers in your country.
4. All movie ids (database ids from Radarr) that are available on one of the chosen streaming services will be deleted and excluded form auto import in the future.

## Dependencies
- Python3
- Radarr v3 (latest develop)
- TMDB account (Free)

## Installation
```bash
git clone https://github.com/haijeploeg/exclude_streaming_radarr.git
pip install -r requirements.txt
```

## Configuration
Open `exclude_streaming_from_radarr.py` and adjust the following values as needed (bear in mind that some settings can be set using an environment variable. e.g. `export TMDB_API_KEY='supersecret'`):

Setting | Value | Set via environment | Default value | Description
---|---|---|---|---
TMDB_API_KEY | str | yes | `supersecret` | Your TMDB API key.
TMDB_LOCALE | str | yes | `NL` | A 2 letter country code. Defaults to: `'NL'`.
RADARR_URL | str | yes | `http://localhost:7878` | The Radarr base url.
RADARR_API_KEY | str | yes | `supersecret` | Your Radarr API key.
RADARR_VERIFY_SSL | bool | yes | `True` | Whether or not to verify the SSL certificate.
RADARR_REMOVE_IF_NOT_FOUND | bool | yes | `True` | If a movie from Radarr is not found on tmdbid (if it is deleted on tmdbid for example) delete this movie too.
RADARR_DELETE_FILES | bool | yes | `True` | Wether tot delete any existing files.
RADARR_ADD_IMPORT_EXCLUSION | bool | yes | `True` | Wether to exclude the movie from any future import.
RADARR_EXCLUDE_PROVIDERS | string | yes | `netflix` | A comma seperated string containing all the streaming services you want to exclude from importing in to radarr. NOT case sensitive. Example `export RADARR_EXCLUDE_PROVIDERS="netflix, amazon prime video, videoland". More info: https://developers.themoviedb.org/3/movies/get-movie-watch-providers

## How to use
Make sure all the variables are exported and set as needed.
```bash
$ python exclude_streaming_from_radarr.py
python exclude_streaming_from_radarr.py
Will remove: 502 - The Old Guard
Deleted 1 movie(s)
```

# Development
This library is still being developed. pytmdb and pyradarr will later be seperate modules.

## Contributing
Feel free to help and contribute to this project :)
