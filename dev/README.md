# Test Excludarr as a user

There is **one manual configuration: [`dev/excludarr.yml`](excludarr.yml)**. Open it in
your editor and change providers, conditions or rules. It is mounted read-only into
the container at `/config/user/excludarr.yml`; your next command sees edits immediately.
No rebuild or `CONFIG=...` selection is needed. The directory mount also picks up
editors that save by atomically replacing the YAML file. CLI, shell and daemon share this file
and `/config/manual.db`. All rules initially have `preview: true`.

Requires Docker Compose and POSIX `make`. Run from the repository root. This stack
contains generated clips, its own named volumes and a separate Plex test account.
It has no indexers or download clients and does not mount a personal library.

## Start and authenticate once

```sh
make dev-up
```

| Service | Local URL | Internal address |
| --- | --- | --- |
| Radarr | http://localhost:17878 | radarr:7878 |
| Sonarr | http://localhost:18989 | sonarr:8989 |
| Plex | http://localhost:32410/web | plex:32400 |
| Tautulli | http://localhost:18181 | tautulli:8181 |
| Seerr | http://localhost:15055 | seerr:5055 |
| Excludarr daemon | http://localhost:18990 | excludarr:8989 |

1. Sign in with a separate Plex **test account**. Get a fresh token from
   https://plex.tv/claim, put `PLEX_CLAIM=claim-...` in the ignored `dev/.env.local`,
   and run within four minutes:

   ```sh
   docker compose -p excludarr-dev --env-file dev/.env.local up -d plex
   ```

2. Open the local Plex URL, name it **Excludarr Dev**, disable remote access and skip
   creating libraries. Remove the temporary claim token from the env file afterwards.
3. Create and match the test libraries before opening the companion wizards:

   ```sh
   docker compose -p excludarr-dev run --rm tools setup-plex
   ```

4. Complete Tautulli using the test account and this Plex server (host `plex`, port
   `32400`, SSL off). Keep the API enabled.
5. Complete Seerr using the same account and Plex address. Add only the local test
   Arr servers from the table. API keys are in their local Settings → General pages;
   select root `/media/movies` or `/media/tv` and disable searches. Leave library sync
   disabled until requests have been seeded if prompted. If server selection fills a
   Docker IP automatically, replace it with `plex` before saving.
6. Run `make dev-seed`.

Credentials and the test username are read from private development volumes and
injected into the YAML's `${...}` placeholders. They are not written into the tracked
YAML or printed by the launcher. Keep the fixed integration addresses and manual.db
path: the launcher refuses other origins or automatic-test databases.

## Everyday commands

```sh
make                                      # Show available shortcuts
make dev ARGS="config validate"
make dev ARGS="preview"                    # All rules, real data, no mutations
make dev ARGS="preview --rule streaming-movies --details"
make dev ARGS="history"
make dev-shell                            # Bash; use ordinary excludarr commands
make dev-down                             # Stop services, preserve data/account setup
```

**To apply a rule:** change only that rule to `preview: false` in `dev/excludarr.yml`,
then run it explicitly by name. `--yes` skips the confirmation; it does not override
`preview: true`. For example:

```sh
# First change the tag rule to preview: false in your editor.
make dev ARGS="run --rule tag --yes"
make dev ARGS="history"
```

Change it back to `preview: true` afterwards. A whole preview can show overlapping
matches: rules execute in file order. Use `--rule NAME` to exercise scenarios individually.

## Manual scenario checklist

For every scenario, start with `make dev ARGS="preview --rule NAME --details"`.
For real actions, enable only the selected rule as described above and then use
`make dev ARGS="run --rule NAME --yes"`. Inspect the corresponding app as well as
Excludarr's report/history.

| Function | Rule / command | Expected result with freshly seeded data |
| --- | --- | --- |
| Provider filtering | `streaming-movies`, `streaming-series` | Shows current Netflix NL matches and monetization evidence; catalogs can change |
| Change providers | Edit `profile.providers` or the explicit provider list in `streaming-series` | Next preview evaluates the changed selection; no rebuild |
| Provider discovery | `make dev ARGS="providers list --locale nl_NL"` | Lists supported provider names and monetization types |
| Tag | `tag` | Forrest Gump gets `dev-checked`; inspect Radarr tags |
| Monitor | `monitor` | Batman Begins becomes monitored; it has no file; search is off |
| Unmonitor | `unmonitor` | Pulp Fiction becomes unmonitored, clip stays |
| Delete files | `files` | The Matrix entry stays, its clip is deleted and monitoring stops |
| Delete + import exclusion | `delete` | Fight Club entry and clip disappear; an Arr import exclusion remains |
| Episode scope | `episode-files` | Breaking Bad S01E01 and S02E01 clips disappear; series stays |
| Season monitoring | `season-unmonitor`, then `season-monitor` | Game of Thrones numbered seasons change monitoring state |
| Whole-series exclusion | `series-exclusion` | Breaking Bad receives a Sonarr import exclusion |
| Metadata/boolean conditions | `metadata` | Forrest Gump matches tag, file, size, date, genre, year and rating through all/any/not |
| Series status | `series-metadata` | Ended Breaking Bad matches and its series gets a tag |
| Keep latest | `trim-seasons`, `trim-episodes` | Older generated units match; run only one scenario before reseeding |
| Watch recency | `recent-watch`, `old-watch` | Toy Story has a recent play; Fellowship has a 90-day-old play |
| Watch user/count/completion + requests | `watch-and-requests` | Breaking Bad S02E01 matches the requesting user's old completed play; tagging affects its parent series |
| Protection / unless | `protected-control` | Zero matches; Empire Strikes Back must not get `dev-should-never-appear` |
| Grace/Plex/rescue | See below | Queue and Leaving Soon membership appear and disappear together |
| Exceptions | Rescue with `--forever` | A later run skips the saved exception until you remove it |
| Lists / unknown policy / HTTP | See below | Included/unknown counts, strict exclusions and authenticated feed JSON |
| Scheduling | See below | Feed every minute; tag rule every five minutes; previews until explicitly enabled |
| Output / sorting | `make dev ARGS="preview --rule metadata --sort title -o json"` | Structured output; `-o yaml` also works |
| Cache | `make dev ARGS="cache status"` | Shows cached facts; use `--refresh` on preview/run to fetch current facts |

The template contains every condition in the current registry and every action type.
Some predicates are intentionally negated: seeded items were added recently and requests
are recent. Change their thresholds and preview to see matches turn into skips.

### Grace, Plex collection and exceptions

Set **only `grace.preview` to false**, keeping `grace_period: 1h`:

```sh
make dev ARGS="run --rule grace --yes"
make dev ARGS="queue"
```

The Dark Knight remains on disk and appears in **Excludarr Dev Leaving Soon** in Plex.
Copy its item key from the queue, replacing `ITEM_KEY` below:

```sh
make dev ARGS="rescue ITEM_KEY --rule grace --once"
make dev ARGS="queue"
```

The queue and collection membership are removed. Requeue it, then test a persistent
exception instead:

```sh
make dev ARGS="run --rule grace --yes"
make dev ARGS="rescue ITEM_KEY --rule grace --forever"
make dev ARGS="exceptions list"
make dev ARGS="run --rule grace --yes"
make dev ARGS="exceptions remove ITEM_KEY --rule grace"
# Rescue removed the queue row; start a new grace period before waiting for expiry.
make dev ARGS="run --rule grace --yes"
make dev ARGS="queue"
```

For actual grace expiry, wait until due and rerun `grace`. Its clip is then removed,
Plex is refreshed and the matching Seerr media/request is cleaned up. The automated
suite advances its clock for this test; the normal CLI uses real time.

### Lists and HTTP

```sh
make dev ARGS="lists preview movies"
make dev ARGS="lists refresh movies"
make dev ARGS="lists status"
make dev-daemon
make dev-feed LIST=movies
make dev ARGS="schedule status"
make dev-daemon-stop
```

`dev-feed` supplies the private feed key internally and prints only the JSON response.
The daemon serves at localhost:18990. CLI `serve` is also available inside `make dev-shell`;
use the daemon shortcut when you want its HTTP port published to the host.

The local source contains IMDb IDs, which JustWatch can use directly: the `movies`
list performs real Netflix filtering without a TMDB token. Known provider matches are
excluded, other known titles included, and unknown streaming results follow its
`on_unknown: include` policy. Counts depend on today's catalog.

`movies-strict` demonstrates missing metadata: its year filter needs a year, which
this IMDb-only source does not supply. Without enrichment it excludes unknown items.
Try `lists preview movies-strict` or refresh it: unknown exclusions produce a nonzero
CLI exit but a published empty snapshot. `make dev-feed LIST=movies-strict` then prints
`[]` while the daemon runs.

To test metadata enrichment, add your test `TMDB_READ_TOKEN` to `dev/.env.local`,
uncomment `list_proxy.tmdb_token` in the YAML, and refresh the list. The year is then
known; these modern fixtures do not match the `year.max: 1900` exclusion. Optional
TMDB Popular/Trending/saved, Trakt and Plex Watchlist source examples are in the same
YAML comments. Add only the source you want, supply its credentials through the ignored
env file, and refer to it from a list. The full source-format reference is
[the list proxy example](../.examples/list-proxy-example.yml). Private saved lists and
cloud watchlists require owner-authorized test-account credentials. Use test lists;
seeding does not change cloud watchlists.

### Scheduling with the same config

```sh
make dev-daemon
make dev ARGS="schedule status"
make dev ARGS="history"
make dev-daemon-stop
```

By default the tag rule is due every five minutes but only previews; `movies` refreshes
every minute. Set `tag.preview: false` for a harmless real scheduled tag action. Restart
with `make dev-daemon` after YAML edits: the daemon reads its config at startup. CLI
commands read it on every invocation. Other rules have no schedule until you add one;
no schedule means manual-only. CLI and daemon share the same database/locks.

## Recover and repeat

```sh
make dev-seed
```

This stops the daemon and restores generated media, metadata, watch fixtures and
requests while preserving account setup **and your edited YAML**. Manual queue,
exceptions and history remain in manual.db, just as they would in normal use. Rescue
queue entries/remove exceptions with the commands above when repeating those scenarios.
Use `--refresh` after reseeding if you want to discard cached facts in your next command.
All rules' preview flags remain as you edited them; set them back to true after actions.

`make dev-up` rebuilds Python tooling after code changes. YAML changes need no rebuild.
Full reset below drops this project's volumes and account setup, but keeps the host YAML:

```sh
docker compose -p excludarr-dev --profile '*' down --volumes
```

You will need a new Plex claim. Do not use global Docker prune commands.

## Automated checks (separate from your config)

```sh
make dev-check
```

This stops the manual daemon and runs destructive scenarios against generated internal
configs (`fixture-preview.yml`, `actions.yml`, `daemon-check.yml`) and separate SQLite
databases. It does not use or overwrite `dev/excludarr.yml` or manual.db. It still changes
the shared test services/files, so run `make dev-seed` afterwards and refresh cached facts.
There is no reason to select an internal config for manual testing.

Offline unit tests remain `.venv/bin/pytest -q`. External catalog availability and actual
playback capture are not deterministic fixture checks. Tautulli history is imported via
its API and dates stay anchored until a full reset; manual playback history is preserved
when seed history is replaced. Search submission can be tested with `search: true`, but
successful downloads need indexers/download clients and are outside this stack.

Pinned images: Radarr 6.4.4.10685, Sonarr 4.0.20.3014, Plex 1.43.5.11079-b3b13e506,
Tautulli 2.19.1, Seerr 3.5.1. Revalidate the suite when upgrading image digests.
