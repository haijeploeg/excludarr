![License](https://img.shields.io/github/license/excludarr/excludarr) [![Docker](https://github.com/excludarr/excludarr/actions/workflows/docker.yml/badge.svg)](https://github.com/excludarr/excludarr/actions/workflows/docker.yml) ![Docker Pulls](https://img.shields.io/docker/pulls/excludarr/excludarr)

# Excludarr

Excludarr is a rule engine for your Radarr and Sonarr libraries. You write rules (conditions plus
an action) in YAML, and Excludarr deletes, unmonitors, monitors, tags or import-excludes the
items that match. "Available on my streaming providers" (JustWatch) is one condition among many.
Others use Radarr/Sonarr data, Tautulli watch history and Seerr requests.

- Radarr and Sonarr plus a JustWatch locale are enough. Tautulli, Seerr and Plex are optional.
- Rules read like a sentence: `any` / `all` / `not` nest freely, and `unless` lists exceptions.
- Items are matched on TMDB/IMDB/TVDB IDs only. Titles are for display.
- Unknown data (failed lookup, no request record, ...) never causes an action.

## Requirements

Python 3.12+ or Docker, Radarr v3+/v5 and/or Sonarr v4.

## Installation

```bash
pip install excludarr
```

Docker:

```bash
docker run --rm -v ./config:/config excludarr/excludarr run
```

The image reads `/config/excludarr.yml` (`EXCLUDARR_CONFIG`) and keeps its SQLite database in
`/config`. With `CRON_MODE=true` it runs `crond` with `/config/crontab` (falling back to a
built-in crontab that runs `excludarr run -y` daily at 02:00). See
`.examples/docker-compose-example.yml`.

cron starts jobs without the container environment, so the entrypoint writes it to
`/etc/excludarr/env.sh`. A custom crontab must source that file first and can send output to the
container log:

```text
0 2 * * * . /etc/excludarr/env.sh && excludarr run -y > /proc/1/fd/1 2>&1
```

## Configuration

Copy `.examples/excludarr-example.yml` to `excludarr.yml`. The config file is the first of:
`--config`, `$EXCLUDARR_CONFIG`, `./excludarr.yml`, `~/.config/excludarr/excludarr.yml`,
`/config/excludarr.yml`, `/etc/excludarr/excludarr.yml`.

- `profile`: `locale` and `providers`, the defaults for every `streaming` condition. List the
  providers with `excludarr providers list --locale nl_NL`.
- `integrations`: `radarr`, `sonarr`, `tautulli`, `seerr`, `plex`. Reference secrets as
  dollar-brace environment variables (`${RADARR_API_KEY}`) inside string values. Every
  placeholder in a value must be set; placeholders in comments are ignored.
- `rules`: run in file order.

Rule fields: `name`, `target` (`radarr`|`sonarr`), `level` (Sonarr: `series`|`season`|`episode`,
default `season`), `when`, `unless`, `action`, `preview` (default `true`), `grace_period`
(default `0`; `<int>h|d|w`), `leaving_soon_collection`, `enabled`.

Actions: `delete`, `delete_files` (keeps the entry so a `monitor` rule can bring it back),
`unmonitor`, `monitor` (`search: true` triggers a search), `tag` (`tag: name`),
`import_exclusion`. `delete` accepts `delete_files` and `import_exclusion` options.

`delete_files` and `monitor` rules work as a pair: `delete_files` removes the files and
unmonitors the entry, and a later `monitor` rule (for example `monitored: false` and
`not: { streaming: my_providers }`) monitors and searches it again. That `monitor` rule also
matches anything you unmonitored by hand, so give it an `unless`. Use `delete` for items that
must not come back: the entry is gone, so no `monitor` rule can match it.

Conditions: `added_more_than`, `added_less_than`, `size_more_than`, `size_less_than`, `tag`,
`genre`, `year`, `rating`, `monitored`, `has_file`, `status` (Sonarr), `keep_latest` (Sonarr),
`streaming`, and with Tautulli `not_watched_for`, `watched_within`, `watched_by`, `play_count`,
`fully_watched`, and with Seerr `requested_by`, `requested_more_than`, `requested_less_than`
and `requester_watched_more_than`. `excludarr config validate` describes each rule in words.

## Safety workflow

1. **Preview.** New rules have `preview: true`. `excludarr run` (or `excludarr preview`) only
   reports the matching items, totals, and per-condition match and unknown counts.
2. **Grace.** Set `preview: false` and optionally a `grace_period`. Matches enter a queue
   (`excludarr queue`) and, with `leaving_soon_collection: true`, a Plex collection. When due they
   are re-evaluated, and only still-matching items are executed. Rescue an item with
   `excludarr rescue KEY --rule NAME --once|--forever`.
3. **Automatic.** With `grace_period: 0` and `preview: false`, matches are executed on every run,
   and each action is written to `excludarr history`.

Unknown condition results never lead to an action. Run `excludarr run --interactive` to
skip individual items from a preview.

## Commands

```text
excludarr [--config PATH] [--debug] [--version] COMMAND
  run [--rule NAME] [--interactive] [-y] [--sort title|size|date]
  preview [--rule NAME] [--sort title|size|date]
  queue [--sort title|size|date]
  rescue ITEM_KEY --rule NAME [--forever | --once]
  history [--limit N]
  exceptions list | remove ITEM_KEY --rule NAME
  providers list [--locale nl_NL]
  config validate
```

## Verify against your setup

The request that adds items to the Plex "Leaving Soon" collection is not verified against a real
Plex server. Try a rule with `preview: false`, a long `grace_period` and
`leaving_soon_collection: true` on a few items before relying on it.

## Migrating from v1

v2 is a breaking release. v1 configs, the `radarr`/`sonarr` commands and the env-var based Docker
configuration are gone, because rules do not fit in environment variables.

- `general.locale` and `general.providers` become `profile.locale` and `profile.providers`.
- `radarr`/`sonarr` url and api_key move under `integrations`. Excluded titles/tags become an
  `unless` block with `tag:`. Titles are no longer matched.
- `radarr exclude` / `sonarr exclude` become a rule with `when: { streaming: my_providers }`
  and an action such as `unmonitor` or `delete_files`.
- `radarr re-add` / `sonarr re-add` become a rule with `action: monitor` and
  `when: { all: [ { monitored: false }, { not: { streaming: my_providers } } ] }`.
- The TMDB API key and `fast_search` are gone. Mount `/config` instead of setting env vars in
  Docker, and call `excludarr run -y` from the crontab.
