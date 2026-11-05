# Excludarr Change History

<!-- version list -->

## 2.0.0 highlights

### Breaking

- Complete rewrite as a rule engine for Radarr/Sonarr (conditions, actions, `unless`).
- v1 YAML configs and the `radarr`/`sonarr` CLI commands are removed. See the README migration notes.
- The Docker image no longer generates its config from environment variables. Mount `/config`.

### Added

- Rules with `all`/`any`/`not` conditions over Radarr/Sonarr, JustWatch, Tautulli and Seerr data.
- Safety workflow: preview by default, grace queue, Plex "Leaving Soon" collection, rescue.
- SQLite storage for queue, exceptions, history and cache.
- Commands: `run`, `preview`, `queue`, `rescue`, `history`, `exceptions`, `providers`, `config`.
- Sonarr season and episode level rules, `keep_latest`, tags, monitor with search, import exclusions.

## 1.1.0

### Fixed

- Fix JustWatch API client. #1

# Prior Versions

- For previous change log see https://github.com/haijeploeg/excludarr/blob/main/CHANGELOG.md
