# Excludarr
By default there is no option to exclude streaming providers from the automatically imported movies throught lists in Radarr. I have created 2 basic API wrappers to connect to Radarr and TMDB (the available API wrappers did not work). This script will do the following:
1. Get a full overview of movies.
2. Exctract the tmdbid value of each movie found.
3. Lookup the extracted `tmdbid` value from Radarr at TMDB itself and check if the movie is available on one of the chosen providers in your country.
4. All movie ids (database ids from Radarr) that are available on one of the chosen streaming services will be deleted and excluded from auto import in the future.

## Dependencies
- Python3
- Radarr v3 (latest)
- TMDB account (Free)

## Installation
```bash
pip install excludarr
```

## Configuration
To configure the application make sure that one of the following files exists:

```
/etc/excludarr/excludarr.yml
~/.config/excludarr/excludarr.yml
~/.excludarr/config/excludarr.yml
~/.excludarr.yml
./.excludarr.yml
```

The application will read those configuration files in that order. So `./.excludarr.yml` will overwrite `/etc/excludarr/excludarr.yml`. For a full list of options and their description see `.excludarr-example.yml` in this repository.

## How to use
Make sure you have setup the configuration file correctly. Read the help page carefully. By default the tool will never delete anything without the `--force` flag specified.

To delete movies you can execute the following:
```bash
$ excludarr exclude -a delete
┏━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┓
┃ ID  ┃ Title                                  ┃ Providers ┃
┡━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━┩
│ 8   │ Outside the Wire                       │ netflix   │
│ 12  │ We Can Be Heroes                       │ netflix   │
│ 13  │ Jumanji: The Next Level                │ netflix   │
│ 17  │ Bad Boys for Life                      │ netflix   │
│ 18  │ The SpongeBob Movie: Sponge on the Run │ netflix   │
└─────┴────────────────────────────────────────┴───────────┘
Are you sure you want to change the status of the movies to: delete? (y/N) y
```

To only change the status to not monitored in radarr:
```bash
$ excludarr exclude -a not-monitored
┏━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┓
┃ ID  ┃ Title                                  ┃ Providers ┃
┡━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━┩
│ 8   │ Outside the Wire                       │ netflix   │
│ 12  │ We Can Be Heroes                       │ netflix   │
│ 13  │ Jumanji: The Next Level                │ netflix   │
│ 17  │ Bad Boys for Life                      │ netflix   │
│ 18  │ The SpongeBob Movie: Sponge on the Run │ netflix   │
└─────┴────────────────────────────────────────┴───────────┘
Are you sure you want to change the status of the movies to: not-monitored? (y/N) y
```

Use the `--help` flag to get more information.

# Development
This library is still being developed. pytmdb and pyradarr will later be seperate modules.

## Contributing
Feel free to help and contribute to this project :)
