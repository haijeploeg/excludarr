<div align="center">

# 🎬 Excludarr

**Keep your Radarr and Sonarr libraries lean, with rules that read like a sentence.**

[![CI](https://github.com/haijeploeg/excludarr/actions/workflows/ci.yml/badge.svg)](https://github.com/haijeploeg/excludarr/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/excludarr)](https://pypi.org/project/excludarr/)
[![PyPI downloads](https://img.shields.io/pypi/dm/excludarr)](https://pypi.org/project/excludarr/)
[![License](https://img.shields.io/github/license/haijeploeg/excludarr)](LICENSE)

![Excludarr demo](docs/demo/demo.gif)

</div>

Already paying for Netflix? Then you don't need that movie on your disk too. Excludarr checks
your library against your streaming services, your watch history and your requests, and
deletes, unmonitors, monitors, tags or import-excludes whatever matches your rules. 🧹

## ✨ Features

- 📺 **Streaming aware**: knows what's on your streaming services in your country, via JustWatch.
- 🧩 **Composable rules**: nest `any`, `all` and `not` freely, and list exceptions under `unless`.
- 👀 **Watch history** (optional): "not watched for 60 days", "fully watched", "watched by Alice", via Tautulli.
- 🙋 **Requests** (optional): "requested by Bob", or "the requester watched it a month ago", via Seerr.
- 🛟 **Safe by default**: new rules only preview. Then a grace period, a Plex "Leaving Soon" collection and a rescue command.
- 🎯 **Season and episode rules** for Sonarr, not just whole series.
- 🔒 **Never guesses**: when a lookup fails or data is missing, nothing happens.
- 🐳 **Runs anywhere**: as a CLI, or in Docker on a cron schedule.

## 🚀 Quick start

**1. Install**

```bash
pip install excludarr
```

**2. Write `excludarr.yml`**

```yaml
profile:
  locale: nl_NL                        # your country
  providers: [Netflix, Disney Plus]    # what you pay for

integrations:
  radarr:
    url: http://radarr:7878
    api_key: ${RADARR_API_KEY}         # read from the environment

rules:
  - name: Streaming movies
    target: radarr
    action: delete_files
    when:
      streaming: my_providers
    unless:
      - tag: keep
```

**3. See what would happen** (nothing is changed)

```bash
excludarr providers list --locale nl_NL   # exact provider names for your country
excludarr config validate                 # describes every rule in plain words
excludarr preview                         # matching items, sizes and reasons
```

**4. Let it act.** Happy with the preview? Set `preview: false` on the rule and run
`excludarr run`. 🎉

## 🐳 Docker

```yaml
services:
  excludarr:
    image: ghcr.io/haijeploeg/excludarr
    environment:
      CRON_MODE: "true"                # run on a schedule (daily at 02:00 by default)
      RADARR_API_KEY: your-api-key
    volumes:
      - ./config:/config               # excludarr.yml, optional crontab, database
```

One-off commands work too:

```bash
docker run --rm -v ./config:/config ghcr.io/haijeploeg/excludarr preview
```

<details>
<summary>Custom schedule</summary>

Put a `crontab` in `/config`. cron starts jobs without the container environment, so source
`/etc/excludarr/env.sh` first. To see the output in `docker logs`, send it to `/proc/1/fd/1`:

```text
0 2 * * * . /etc/excludarr/env.sh && excludarr run -y > /proc/1/fd/1 2>&1
```

</details>

## 🍳 Recipes

Every recipe below is a complete rule for the `rules:` list. Combine as many as you like; they
run in file order.

### 📺 Unmonitor what you can stream, and get it back when it leaves

```yaml
- name: Streaming movies
  target: radarr
  action: delete_files          # deletes the files, keeps the entry in Radarr
  when:
    streaming: my_providers

- name: Back when it leaves streaming
  target: radarr
  action: monitor
  search: true                  # and search for it right away
  when:
    all:
      - monitored: false
      - not: { streaming: my_providers }
  unless:
    - tag: unmonitored-by-hand
```

### ⏳ Give people two weeks' notice in Plex

```yaml
- name: Streaming movies
  target: radarr
  preview: false
  grace_period: 14d             # wait 14 days, then check again before acting
  leaving_soon_collection: true # show the queue as a Plex collection
  action: delete_files
  when:
    streaming: my_providers
```

### 🕸️ Clear out what nobody watches (Tautulli)

```yaml
- name: Stale movies
  target: radarr
  action: delete
  delete_files: true
  import_exclusion: true        # stop lists from adding it back
  when:
    all:
      - added_more_than: 180d
      - not_watched_for: 90d
  unless:
    - tag: keep
```

### 🙋 Remove requests once the requester has watched them (Seerr + Tautulli)

```yaml
- name: Watched requests
  target: radarr
  action: delete
  delete_files: true
  when:
    requester_watched_more_than: 30d
```

### 📚 Remove seasons nobody has watched in a while

```yaml
- name: Unwatched seasons
  target: sonarr
  level: season                 # series | season | episode
  action: delete_files
  when:
    all:
      - added_more_than: 90d
      - not_watched_for: 60d
```

### ✂️ Keep only the latest two seasons of ended shows

```yaml
- name: Trim old seasons
  target: sonarr
  level: season
  action: unmonitor
  when:
    all:
      - keep_latest: { seasons: 2 }   # matches the seasons NOT among the latest 2
      - status: ended
  unless:
    - genre: [Anime, Documentary]
```

### 🏷️ Tag big movies with a low rating for a manual look

```yaml
- name: Review candidates
  target: radarr
  action: tag
  tag: review
  when:
    all:
      - size_more_than: 20GB
      - not: { rating: { source: imdb, min: 6.0 } }
```

More examples are in [`.examples/excludarr-example.yml`](.examples/excludarr-example.yml).

## 🛟 Safety first

Excludarr deletes things, so it starts out cautious:

1. 👁️ **Preview.** New rules have `preview: true`. They only report what they would do: matching
   items, total size, and how many items each condition matched (or couldn't tell).
2. ⏳ **Grace.** Set `preview: false` and a `grace_period`. Matches go into a queue
   (`excludarr queue`) and, if you like, a Plex "Leaving Soon" collection. When the grace period
   ends, each item is checked again, and only items that still match are acted on. Changed your
   mind? `excludarr rescue KEY --rule NAME --once` (or `--forever`).
3. 🤖 **Automatic.** With `preview: false` and no grace period, matches are acted on at every run.
   Everything ends up in `excludarr history`.

When a lookup fails or data is missing, the condition counts as unknown, and unknown never
leads to an action.

## 📖 Reference

<details>
<summary><b>Commands</b></summary>

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

`run --interactive` lets you skip individual items.

</details>

<details>
<summary><b>Configuration file</b></summary>

Excludarr uses the first file it finds: `--config`, `$EXCLUDARR_CONFIG`, `./excludarr.yml`,
`~/.config/excludarr/excludarr.yml`, `/config/excludarr.yml`, `/etc/excludarr/excludarr.yml`.

- `profile`: `locale` and `providers`, the defaults for every `streaming` condition.
- `integrations`: `radarr` and/or `sonarr` (at least one), plus optional `tautulli`, `seerr`
  and `plex`. Write secrets as `${ENV_VAR}`. Every placeholder in a value must be set;
  placeholders in comments are ignored.
- `rules`: run in file order.

</details>

<details>
<summary><b>Rule fields</b></summary>

| Field | Meaning |
|---|---|
| `name` | Unique name, used by `--rule` and `rescue` |
| `target` | `radarr` or `sonarr` |
| `level` | Sonarr only: `series`, `season` (default) or `episode` |
| `when` | Conditions that must be true |
| `unless` | List of exceptions; any true one skips the item |
| `action` | `delete`, `delete_files`, `unmonitor`, `monitor`, `tag`, `import_exclusion` |
| `preview` | `true` (default) only reports |
| `grace_period` | `0` (default) or `<number>h`, `d` or `w` |
| `leaving_soon_collection` | Show queued items in a Plex collection |
| `enabled` | `false` skips the rule |

Action options: `delete` takes `delete_files: true` and `import_exclusion: true`; `monitor`
takes `search: true`; `tag` takes `tag: name`.

`delete_files` keeps the entry, so a `monitor` rule can bring it back later. Use `delete` for
things that should stay gone.

</details>

<details>
<summary><b>Conditions</b></summary>

| Condition | Example | Needs |
|---|---|---|
| `streaming` | `my_providers` or `{ providers: [Netflix], monetization: [flatrate, free] }` | |
| `added_more_than` / `added_less_than` | `180d` | |
| `size_more_than` / `size_less_than` | `20GB` | |
| `tag` / `genre` | `keep` or `[Anime, Documentary]` | |
| `year` | `{ min: 1990, max: 2010 }` | |
| `rating` | `{ source: imdb, min: 6.0 }` | |
| `monitored` / `has_file` | `true` | |
| `status` | `ended` or `continuing` | Sonarr |
| `keep_latest` | `{ seasons: 2 }` (level `season`) or `{ episodes: 5 }` (level `episode`) | Sonarr |
| `not_watched_for` / `watched_within` | `60d` | Tautulli |
| `watched_by` | `alice` | Tautulli |
| `play_count` | `{ max: 0 }` | Tautulli |
| `fully_watched` | `true` | Tautulli |
| `requested_by` | `bob` | Seerr |
| `requested_more_than` / `requested_less_than` | `30d` | Seerr |
| `requester_watched_more_than` | `30d` | Seerr + Tautulli |

Combine them with `all: [...]`, `any: [...]` and `not: {...}`.

</details>

<details>
<summary><b>Migrating from v1</b></summary>

v2 is a breaking release: v1 configs, the `radarr`/`sonarr` commands and the Docker
configuration through environment variables are gone.

- `general.locale` and `general.providers` become `profile.locale` and `profile.providers`.
- The `radarr`/`sonarr` URL and API key move under `integrations`. Excluded titles and tags
  become an `unless` block with `tag:`. Titles are no longer matched.
- `radarr exclude` / `sonarr exclude` become a rule with `when: { streaming: my_providers }` and
  an action such as `unmonitor` or `delete_files`.
- `radarr re-add` / `sonarr re-add` become a rule with `action: monitor` and
  `when: { all: [ { monitored: false }, { not: { streaming: my_providers } } ] }`.
- The TMDB API key and `fast_search` are gone. In Docker, mount `/config` instead of setting
  environment variables, and call `excludarr run -y` from the crontab.

</details>

## ⚠️ Not yet verified

Adding items to the Plex "Leaving Soon" collection hasn't been tested against a real Plex
server yet. Try it on a few items, with a long `grace_period`, before relying on it.

## 🤝 Contributing

See [DEVELOPER.md](.github/DEVELOPER.md) for running tests, the demo recording and how releases
work.
