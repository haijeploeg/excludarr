# Excludarr Change History

<!-- version list -->

## v2.4.0 (2026-11-13)

### Features

- **plex**: Add seasons and episodes to the Leaving Soon collection
  ([`021a35e`](https://github.com/haijeploeg/excludarr/commit/021a35e6e8c6e34e06b7870f7917a9e4f18469f3))


## v2.3.0 (2026-11-13)

### Bug Fixes

- Make CLI tests color-safe and restore dev scenarios
  ([`fcc6892`](https://github.com/haijeploeg/excludarr/commit/fcc6892cfced93f3c74d0a0ed159a911e555dcdd))

### Features

- Add daemon scheduler and seeded development environment
  ([`8a7562b`](https://github.com/haijeploeg/excludarr/commit/8a7562ba6a04ce426359bbc06d82bf6a01b80ce4))


## v2.2.0 (2026-11-11)

### Features

- Add filtered list proxy for Radarr and Sonarr
  ([`6087b41`](https://github.com/haijeploeg/excludarr/commit/6087b4167a3071725dab0218061e03e67c79412b))


## v2.1.0 (2026-11-11)

### Continuous Integration

- Group all dependabot updates into one PR
  ([`afe8ea5`](https://github.com/haijeploeg/excludarr/commit/afe8ea578a37b6aad2c8a3f211d4dd27263fc53e))

- Only bump pip requirements when needed
  ([`664e18b`](https://github.com/haijeploeg/excludarr/commit/664e18bd83506848a095d97f8ec140d24406438b))

### Documentation

- Refresh README with demo and recipes
  ([`527c295`](https://github.com/haijeploeg/excludarr/commit/527c295d039b422205d4e96fed7e3286d902d807))

### Features

- **cli**: Add detailed reporting and preview outcome predictions
  ([`f4ec193`](https://github.com/haijeploeg/excludarr/commit/f4ec1936bf46e75375bf9544f42689abf01ef03e))

### Testing

- Compare --version against __version__
  ([`1007254`](https://github.com/haijeploeg/excludarr/commit/10072544183a58dddddaed864c02c3bf6fd4ee0a))


## v2.0.1 (2026-11-05)

### Bug Fixes

- **docker**: Bump python from 3.12-alpine to 3.15-alpine
  ([`6017924`](https://github.com/haijeploeg/excludarr/commit/60179244b412812ae66efa8cb92e623a3de7127c))


## v2.0.0 (2026-11-05)

### Bug Fixes

- Migrate justwatch api calls to simple-justwatch-python-api client
  ([`cae06b0`](https://github.com/haijeploeg/excludarr/commit/cae06b008f013e3d40a1d014d7629ad9267b1760))

- **config**: Substitute ${VAR} after YAML parsing
  ([`81e9bd1`](https://github.com/haijeploeg/excludarr/commit/81e9bd167f56c4ece01ffec257d183349f0dc0bd))

- **justwatch**: Replace removed REST endpoints with GraphQL
  ([`62edb09`](https://github.com/haijeploeg/excludarr/commit/62edb091f772efe4c763730570dbc0db6b8534b6))

### Build System

- Add Dockerfile to build a patched image on top of the published one
  ([`65595a7`](https://github.com/haijeploeg/excludarr/commit/65595a7e6e6a9bd1c8d3eadbfd0c46e7c3c9d60c))

### Chores

- Import excludarr v1.1.3 source from published docker image
  ([`efcdf92`](https://github.com/haijeploeg/excludarr/commit/efcdf92460622e8a5df78dda183bda6d330863e0))

- Track CLAUDE.md and superpowers docs
  ([`4987d14`](https://github.com/haijeploeg/excludarr/commit/4987d147d5e8dd11e3746d6d02206846fd7a0ddc))

### Continuous Integration

- Automate releases with python-semantic-release
  ([`b51b436`](https://github.com/haijeploeg/excludarr/commit/b51b436cd1741da153f0157c6126e0306966d741))

### Documentation

- Describe rebase-only merges for releases
  ([`ca0c990`](https://github.com/haijeploeg/excludarr/commit/ca0c9901ff93693bf85031733e8e6d62e9f435ff))

### Features

- V2 rewrite with YAML library rules engine
  ([`0cacba5`](https://github.com/haijeploeg/excludarr/commit/0cacba5b063e2b3c3183a964aff3adc159d2af10))

### Breaking Changes

- V1 CLI and configuration are replaced.


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
