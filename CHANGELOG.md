# Excludarr Change History

## 1.0.1

### Fixed

- Build process to PyPi and Docker

## 1.0.0

### Added

- Full rewrite of excludarr using Typer
- Debug logging using the `--debug` parameter
- Add JustWatch as the source of all the data
- TMDB is not mandatory anymore, but can be used as a fallback option if the title could not be found using JustWatch.
- Add season and individually episode support #21
- Add re-add functionality
- Add exclude support to exclude titles from being processed by Excludarr #24
- Update Docker image
- Add progress bar

### Fixed

- Minor bugs
- Overall error handling
- Automatically fallback to legacy delete functionality in Radarr. This removes the `--legacy` flag.
- Fast searching using the JustWatch API

### Removed

- Cement library was removed

## 0.2.1

### Fixed

- Fix list index out of range in Sonarr.

## 0.2.0

### Added

- The exclude command now support Sonarr to exclude series.

## 0.1.5

### Added

- Add a check command to re-add not-monitored movies to monitored if they are not present on a configured streaming provider.

## 0.1.4

### Fixed

- Minor bug with the `-f` flad in combination with the not-monitored status.

## 0.1.3

### Added

- Add Docker image and build process

## 0.1.2

### Added

- Add not-monitored support

## 0.1.1

### Added

- Release to PyPi.

## 0.1.0

### Added

- Rewritten the tool to a full CLI tool
- Add more flexibility by adding flags
- The tool will not delete movies without asking the user
