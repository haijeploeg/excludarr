# Excludarr
Excludarr is a CLI that interacts with Radarr and Sonarr instances. It completely manages you library in Sonarr and Radarr to only consist out of movies and series that are not present on any of the configured streaming providers. Excludarr can also re monitor movies and series if it is not available anymore on any of the configured streaming providers. You can also configure to delete the already downloaded files of the excluded entry to keep your storage happy! 🎉

## Installation
Installation of excludarr can be done using pip.

```bash
pip install excludarr
```

## Configuration
To configure the application make sure that one of the following files exists:

```bash
/etc/excludarr/excludarr.yml
~/.config/excludarr/excludarr.yml
~/.excludarr/config/excludarr.yml
~/.excludarr.yml
./.excludarr.yml
```

The application will read those configuration files in that order. So `./.excludarr.yml` will overwrite `/etc/excludarr/excludarr.yml`. For a full list of options and their description see [.excludarr-example.yml](https://github.com/haijeploeg/excludarr/blob/main/.excludarr-example.yml) in this repository.

> NOTE: To get a full list of available providers in your country, execute `excludarr providers list` and copy the full name of the provider in your configuration.

## Radarr
The `radarr` subcommands manages the library in your configured Radarr instance. Check `excludarr radarr --help` for a full list of options.

### Exclude
To delete or disable monitoring of the movies in Radarr you can execute the `excludarr radarr exclude` command. You can determine to either delete the movie or change the status to not monitored. You can alo configure if you want to delete the associated files and to add an import exclusion to prevent future importing of the movie.

By default no files are being deleted, you have to set the `-d` flag. To make the command non-interactive you can pass the `-y` flag to auto accept the confirmation question. To show the progress of the process you can pass the `--progress` flag to get a nice progress bar! Read the help page of the command carefully to adjust the command to your needs.

```bash
$ excludarr radarr exclude -a delete -d -e
              ╷                                            ╷                ╷
 Release Date │ Title                                      │ Used Diskspace │ Streaming Providers
╶─────────────┼────────────────────────────────────────────┼────────────────┼─────────────────────────────────╴
 2021-11-04   │ Red Notice                                 │ 0.00GB         │ Netflix
 2021-10-13   │ The Last Duel                              │ 0.00GB         │ Apple iTunes
 2021-11-04   │ Amina                                      │ 0.00GB         │ Netflix
 2021-11-25   │ Apex                                       │ 12.00GB        │ Apple iTunes
 2021-11-25   │ A Boy Called Christmas                     │ 0.00GB         │ Netflix
 2012-06-27   │ The Amazing Spider-Man                     │ 0.00GB         │ Netflix, Apple iTunes
 2017-07-05   │ Spider-Man: Homecoming                     │ 7.50GB         │ Apple iTunes
 2021-10-22   │ The Harder They Fall                       │ 0.00GB         │ Netflix
 2021-12-02   │ Single All the Way                         │ 0.00GB         │ Netflix
 2021-05-19   │ F9                                         │ 0.00GB         │ Apple iTunes
 2021-07-28   │ The Suicide Squad                          │ 10.00GB        │ Apple iTunes
 2021-10-29   │ Army of Thieves                            │ 0.00GB         │ Netflix
 2021-08-09   │ PAW Patrol: The Movie                      │ 0.00GB         │ Apple iTunes
 2018-12-06   │ Spider-Man: Into the Spider-Verse          │ 20.00GB        │ Apple iTunes
 2002-05-01   │ Spider-Man                                 │ 0.00GB         │ Netflix, Apple iTunes
╶─────────────┼────────────────────────────────────────────┼────────────────┼─────────────────────────────────╴
              │                       Total Used Diskspace │ 49.50GB        │
              ╵                                            ╵                ╵
Are you sure you want to delete the listed movies? [y/n] (n): y
Succesfully deleted the movies from Radarr!
```

> NOTE: If you want to exclude any of the movies listed in the table, just copy the title and paste it in your configuration file under `radarr -> excludes`.

### Re-add
To re enable monitoring of not-monitored movies in Radarr that are not present anymore on any of the streaming providers, you can execute `excludarr radarr re-add`. This will lookup all movies that are not monitored anymore in Radarr and check if they are still available on the configured streaming providers. If there is no match, the status of the movie will change to monitored. This is handy if you remove a streaming provider from the configuration, or if the movie is being deleted from a streaming provider.

```bash
$ excludarr radarr re-add
              ╷
 Release Date │ Title
╶─────────────┼───────────────────────────────────────────╴
 2021-08-27   │ Vacation Friends
 2021-10-13   │ The Last Duel
 2021-09-01   │ Shang-Chi and the Legend of the Ten Rings
 2021-06-17   │ Luca
 2019-06-28   │ Spider-Man: Far From Home
 2021-11-12   │ Home Sweet Home Alone
 2021-07-07   │ Black Widow
 2021-07-22   │ Snake Eyes: G.I. Joe Origins
 2021-07-28   │ Jungle Cruise
 2020-08-04   │ Deathstroke: Knights & Dragons - The Movie
 2021-05-19   │ F9
 2021-07-28   │ The Suicide Squad
 2021-08-09   │ PAW Patrol: The Movie
 2021-09-03   │ Zone 414
 2021-05-26   │ Cruella
 2021-07-15   │ Space Jam: A New Legacy
 2021-03-24   │ Godzilla vs. Kong
              ╵
Are you sure you want to re monitor the listed movies? [y/n] (n): y
Succesfully changed the status of the movies listed in Radarr to monitored!
```

## Sonarr
The `sonarr` subcommands manages the library in your configured Sonarr instance. Check `excludarr sonarr --help` for a full list of options.

### Exclude
### re-add
