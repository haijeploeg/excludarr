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
- 🔒 **Library actions require known data**: an unknown rule result never executes an action.
- 📋 **[Filtered import lists](docs/list-proxy.md)**: serve feeds to Radarr/Sonarr; configure whether unknown filter results are included or excluded.
- 🐳 **Runs anywhere**: one-shot CLI, legacy cron, or a [single daemon](docs/daemon.md) with per-list/per-rule cron schedules.

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

## Filtered list proxy

Filter source lists **before** Radarr/Sonarr import titles. Sources include Trakt
Popular/Trending, saved lists and Watchlist; StevenLu; Plex Watchlist; and TMDB
Popular/Trending and saved lists.

See the **[list proxy setup guide](docs/list-proxy.md)** for credentials, a minimal
config, CLI and Docker startup, exact feed URLs, output meanings and troubleshooting.
Start with [the minimal two-feed config](.examples/list-proxy-quickstart.yml);
[the complete source example](.examples/list-proxy-example.yml) is a reference for
adding more sources.

`excludarr lists refresh` updates stored feeds and exits. `excludarr serve` stays
running and serves them under `/lists/NAME?apikey=YOUR_FEED_KEY`; it does not refresh
them. Run both independently, with the same config and database. The guide's Docker
example uses a server container and an hourly refresh container.

## Daemon and scheduling

Run `excludarr daemon` for one persistent process serving feeds and executing
individual list/rule cron schedules. Existing preview and grace settings remain
in force. Inspect local results with `excludarr schedule status`.

See [the daemon setup and migration guide](docs/daemon.md),
[the complete scheduled config](.examples/daemon-example.yml) and
[the one-container Compose example](.examples/daemon-compose.yml).
The separate `serve` and cron workflow remains available.

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
  run [--progress] [--details] [--refresh] [--type movies|series] [--rule NAME] [--interactive] [-y] [--sort title|size|date]
  preview [--progress] [--details] [--refresh] [--type movies|series] [--rule NAME] [--sort title|size|date]
  queue [--sort title|size|date]
  rescue ITEM_KEY --rule NAME [--forever | --once]
  history [--limit N]
  cache status
  rating-keys prune
  exceptions list | remove ITEM_KEY --rule NAME
  providers list [--locale nl_NL]
  config validate
```

`--type movies` selects Radarr rules, and `--type series` selects Sonarr rules at every level.
Without `--type`, both are included. You can combine it with `--rule`.
The global `--debug` option also shows unknown results and counts for individual conditions.
Use `excludarr --debug preview --rule "RULE NAME"` to log JustWatch candidates,
ID matches, cached results and offers. Requester watch conditions also log whether
they found a Seerr request and usable Plex/Tautulli watch data.
When the configured JustWatch search locale has no matching TMDB or IMDb ID, Excludarr
also searches `en_US`. Offers are always checked in the configured locale.
`run --interactive` lets you skip individual items.

Preview describes each rule's action and related cleanup. The `Next step` column predicts
the configured actions and grace queue behavior, including newly queued items, future due
dates and items due now. The preview command simulates actions even for rules with
`preview: true`, without prompts or changes to media, queue entries or action history.
Its banner explains that execution requires `run`; it also names rules that must first
be changed to `preview: false`. Dates are UTC.
Later matches covered by an earlier immediate removal are marked as skipped, assuming that
the earlier action succeeds.

`Matched size` is the size of matching media. The separate estimated space savings count
each movie or Sonarr file once across rules, seasons and episodes. Savings are split between
immediate execution and additional space after grace periods. Actions that keep files
contribute zero. Unique titles count each movie or parent series once.
Estimates use the current library snapshot, assume confirmed successful actions, and do not
guarantee future savings because queued items are re-evaluated when due.

Preview and run results show every match in a table that adapts to the terminal width.
Each row shows the title, rule, size, match evidence and planned step or result.
Add `--details` for extra context such as labels, file age, viewers and Seerr requests. Streaming
context is limited to providers in `profile.providers` for the configured locale. Viewer
details require Plex and Tautulli. Seerr request details include status and requester when
available. Queue and history entries retain match evidence from when they were queued or acted
on. History reports the bytes freed by the action separately from the original item size.

Use `-o json` or `-o yaml` on the commands above for one complete report on stdout.
Structured reports include all available match context regardless of `--details`.
Confirmation and progress go to stderr. Pass `run -y` for unattended execution.

Add `--progress` to `run` or `preview` to show the current phase, API waits, elapsed time
and completed/total counts where available. The display pauses during confirmation.

Run `excludarr cache status` to inspect when the local JustWatch cache was fetched and when
it expires. Expired entries refresh the next time they are used. With `--debug`, cache
status lists individual entries and preview or run logs lookups and retries. Add
`--refresh` to preview or run to bypass cached JustWatch values for the selected operation.
Failed refreshes leave existing cache entries intact and those values are unavailable to that run.

Watch history stays known after Plex removes or re-adds an item. Excludarr stores every Plex
rating key it sees for an item and matches Tautulli history on all of them. This starts from
the first run after the upgrade. Run `excludarr rating-keys prune` to delete the stored keys of
items that Radarr and Sonarr no longer have. It deletes nothing if Radarr or Sonarr fails.

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
| `streaming` | `my_providers` or `{ providers: [Netflix], monetization: [flatrate, free], min_quality: hd }` | |
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

## Minimum streaming quality

Set `min_quality` inside a streaming condition to require `sd`, `hd` or `4k`:

```yaml
when:
  streaming:
    providers: [Netflix]
    monetization: [flatrate]
    min_quality: hd
```

These are minimums: `hd` accepts HD and 4K. Without `min_quality`, availability
matching stays unchanged. The provider, monetization and quality must belong to
the same offer; a 4K purchase cannot qualify an SD subscription. For a season,
every selected episode must meet the minimum. Rules run manually or by the daemon
use the same condition. Preview shows the minimum and qualifying offer quality.

Missing or unfamiliar quality makes an otherwise eligible offer unknown. Unknown
streaming cannot establish a destructive match, including under `not`. JustWatch
reports catalog quality, not the quality available to your account or device.
There are no separate 720p/1080p, HDR or audio thresholds. On upgrade, offers are
refetched once as needed; existing title matches and cache expiry settings stay.

## ⚠️ Not yet verified

Adding items to the Plex "Leaving Soon" collection hasn't been tested against a real Plex
server yet. Try it on a few items, with a long `grace_period`, before relying on it.

## 🤝 Contributing

See [DEVELOPER.md](.github/DEVELOPER.md) for running tests, the demo recording and how releases
work.

## Development integration environment

The repository includes a [disposable full-suite development stack](dev/README.md)
with real Radarr, Sonarr, Plex, Tautulli and Seerr, generated test clips and repeatable
fixtures. Preview, destructive actions and daemon checks can run there without using
an existing library. Plex-related checks need a separate test account and one-time setup.

Use `make` to list development shortcuts, `make dev ARGS="preview"` to run the CLI
inside the stack, and `make dev-shell` for an interactive shell. See the stack guide
for one-time setup and manual scenarios. Edit `dev/excludarr.yml` directly; all rules
start in preview, and CLI/shell/daemon use the same file without a rebuild.
