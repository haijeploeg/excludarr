# List proxy: setup and daily use

Excludarr reads source lists, filters their titles, and serves the remaining titles
as import lists for Radarr and Sonarr. It does not add titles to either library
itself: Radarr/Sonarr fetch the feeds on their own schedule.

For built-in per-list scheduling and a one-container deployment, use the
[daemon guide](daemon.md). The manual `refresh` + `serve` workflow below remains
supported; do not run both schedulers against the same deployment.

The workflow is **configure → preview → refresh → serve → connect Radarr/Sonarr**.
`refresh` and `serve` are separate commands: one updates stored data and exits;
the other stays running and serves that data.

## 1. Configure two feeds

Copy [the minimal config](../.examples/list-proxy-quickstart.yml) to `excludarr.yml`.
It combines TMDB Trending movies and TMDB Popular series with a Netflix filter.
Change the locale, providers and integration URLs to your own setup. Find exact
provider names with `excludarr providers list --locale nl_NL`.

The config still requires at least one Radarr/Sonarr integration. Keep your
existing `integrations` when adding `list_proxy` to an existing config. Library
`rules` can coexist with feeds, but `lists refresh` and `serve` never execute them.
If you use only one arr, remove the other integration; you can also remove its
outgoing list and unused source.

The example needs four environment variables:

| Variable | Where it comes from | Purpose |
| --- | --- | --- |
| `LIST_PROXY_API_KEY` | Generate your own random key | Radarr/Sonarr authenticate to Excludarr's feeds |
| `TMDB_READ_TOKEN` | TMDB account → Settings → API → **API Read Access Token** | Excludarr reads TMDB lists and resolves external IDs |
| `RADARR_API_KEY` | Radarr → Settings → General | Existing Radarr integration configuration |
| `SONARR_API_KEY` | Sonarr → Settings → General | Existing Sonarr integration configuration |

Generate the feed key once:

```bash
openssl rand -hex 32
```

Save the result and use that same value for `LIST_PROXY_API_KEY` and the `apikey`
query parameter in the feed URLs. This is **not** your TMDB token or Radarr API key.
Public TMDB lists still require application authentication. This implementation
expects the long **API Read Access Token**, not the shorter v3 API key.
See [TMDB's authentication guide](https://developer.themoviedb.org/docs/authentication-application).

For a local CLI session, export the values before running Excludarr:

```bash
export LIST_PROXY_API_KEY='paste-your-generated-feed-key'
export TMDB_READ_TOKEN='paste-your-tmdb-read-access-token'
export RADARR_API_KEY='paste-your-radarr-key'
export SONARR_API_KEY='paste-your-sonarr-key'
```

Excludarr expands `${VAR}` in YAML. It does **not** automatically load a local
`.env` file; Docker Compose can load one using `env_file`, as shown below. Remove
unused sources from the config too: variables in unused source definitions are
still expanded and validated.

## 2. Preview and publish

Run these from the directory containing `excludarr.yml`, or put
`--config /path/to/excludarr.yml` before the subcommand.

```bash
excludarr config validate
excludarr lists preview movies
excludarr lists preview series
excludarr lists refresh
excludarr lists status
```

| Command | What it does |
| --- | --- |
| `lists preview NAME` | Fetch and evaluate one list without replacing its published snapshot; normal lookup caches may change |
| `lists refresh [NAME]` | Fetch, filter and publish one or all lists, then exit; does not start the server |
| `lists status` | Read local snapshot age, validity, counts and the last refresh error; no upstream requests |
| `serve` | Keep an HTTP server running; does not refresh lists |

The keys under `list_proxy.lists` are the outgoing feed names. The example has
`movies` and `series`. Those names determine the paths `/lists/movies` and
`/lists/series`. Renaming a key changes its feed path.

### Reading the results

- **included** (green): the title goes into the outgoing feed for Radarr/Sonarr.
- **excluded** (yellow): the title is left out. The reason may be a filter match
  such as `Netflix · subscription`, or a missing export ID.
- `no qualifying offers … false`: the streaming condition did not match your
  configured providers/offer types. For the example filter, that means include.
- `Required data unavailable`: the filter could not be decided. By default the
  title is included; JSON/YAML marks it with `unknown: true`.

`when` describes what to **exclude**, not what to import. `unless` protects
exceptions from exclusion. To exclude titles when filter data is unavailable,
set `on_unknown: exclude` on the outgoing list. The default is `include`.

Movies need an IMDb ID and series need a TVDB ID for export. Excludarr attempts
to resolve them through TMDB. If an ID is still missing, only that title is
excluded with a reason; the other titles are published. `on_unknown: include`
cannot make a title without an export ID importable.

All three `lists` commands accept `-o json` or `-o yaml` for complete reports.
Refresh/preview exit nonzero for a refresh failure or an unknown decision blocked
with `on_unknown: exclude`. In the latter case, the evaluated feed is still
published. Missing export IDs are individual exclusions and do not fail refresh.

## 3. Start the server and connect your arrs

```bash
excludarr serve
```

The default is `127.0.0.1:8989`. Startup prints each configured feed's name, target
and URL, followed by the authentication instructions. Keep this process running.
On the same machine, the example feeds are:

```text
http://127.0.0.1:8989/lists/movies?apikey=YOUR_FEED_KEY
http://127.0.0.1:8989/lists/series?apikey=YOUR_FEED_KEY
```

Replace `YOUR_FEED_KEY` with `LIST_PROXY_API_KEY`. A generated hex key needs no URL
encoding; other keys must be URL-encoded. Feeds are not at `/`, `/movies` or
`/series`. One server process serves every configured list.

In Radarr, add a **StevenLu Custom** import list with the movies URL. In Sonarr,
add a **Custom List** with the series URL. Set the quality profile, root folder,
monitoring and automatic-add settings in the respective arr.

If Radarr/Sonarr run on another machine or in Docker, `127.0.0.1` refers to
**their own machine/container**, not Excludarr. Bind Excludarr to a reachable
interface and use the Excludarr host's LAN address or a shared Docker-network
service name:

```bash
excludarr serve --host 0.0.0.0 --port 8990
```

For that example, use `http://YOUR_EXCLUDARR_HOST:8990/lists/movies?apikey=YOUR_FEED_KEY`.
`0.0.0.0` is the bind address, not the hostname to enter in Radarr/Sonarr. Choose a
free port: Sonarr commonly already occupies 8989 on its host.

## 4. Keep feeds fresh

Keep `serve` running and run `excludarr lists refresh` separately, for example
every hour via cron. A successful snapshot is usable for **six hours**. Availability
can change between refreshes; this is not a live lookup on each feed request.

A failed source download or conflicting identity preserves that outgoing list's
previous snapshot without renewing its lifetime. Other outgoing lists can still
refresh successfully. An empty successful feed returns HTTP 200 with `[]`;
missing, expired or incompatible snapshots return HTTP 503.

After changing config or credentials, restart `serve` and run `lists refresh`.
Existing snapshots may no longer match the new configuration. Use the same config,
environment variables and database for the refresh and server processes. By
default the database is `excludarr.db` beside the config file; `database` can
explicitly override it.

## Docker Compose

Create a directory with these files, copied from the linked examples:

```text
proxy/
  compose.yml             ← .examples/list-proxy-compose.yml
  list-proxy-crontab       ← .examples/list-proxy-crontab
  .env                    ← credentials below
  config/
    excludarr.yml         ← .examples/list-proxy-quickstart.yml
```

Links: [Compose](../.examples/list-proxy-compose.yml),
[hourly crontab](../.examples/list-proxy-crontab),
[minimal config](../.examples/list-proxy-quickstart.yml).

Put the four variables from step 1 in `.env`, without `export`:

```dotenv
LIST_PROXY_API_KEY=paste-your-generated-feed-key
TMDB_READ_TOKEN=paste-your-tmdb-read-access-token
RADARR_API_KEY=paste-your-radarr-key
SONARR_API_KEY=paste-your-sonarr-key
```

Use an image containing the list proxy commands. For an unreleased checkout,
run `docker build -t excludarr:dev .` in the repository and change **both** image
entries in `compose.yml` to `excludarr:dev`.

From the `proxy/` directory, publish the first snapshots, then start both services:

```bash
docker compose run --rm --no-deps list-server lists refresh
docker compose up -d
docker compose exec list-server excludarr lists status
docker compose logs -f list-refresh
```

`list-server` serves HTTP; `list-refresh` runs the hourly cron job. Both share
`./config:/config`, credentials and SQLite file permissions. The entrypoint runs
either cron or the CLI command; a single container does not run both modes.
The cron job uses `/etc/excludarr/env.sh` to load the container environment.

The example publishes host port **8989**. If occupied, change only the host side,
e.g. `"8990:8989"`, and use port 8990 in URLs via the host address. Arr containers
on the **same Docker network** can use `http://list-server:8989/lists/movies?apikey=YOUR_FEED_KEY`.
Containers in unrelated Compose projects cannot resolve `list-server` by default;
use a reachable host address or explicitly connect them to a shared network.

After editing `.env`, recreate the containers with `docker compose up -d --force-recreate`
and refresh again. A container restart alone does not reload its environment file.

## More sources and filters

[The complete source example](../.examples/list-proxy-example.yml) includes all
supported modes. It is a reference, not a ready-to-run account setup: replace the
saved-list IDs and remove sources you do not use, along with their list references.

| Source | Supported input | Credentials |
| --- | --- | --- |
| Trakt | Popular/Trending movie or series charts, saved lists by user/list ID or slug, authenticated Watchlist | `client_id`; `token` for private lists/Watchlist |
| StevenLu | Public movie feed, optionally a compatible `url` | None for the source itself |
| Plex Watchlist | The token owner's online movie/show Watchlist | Source `token`, separate from the local Plex integration |
| TMDB | Popular/Trending movie or series charts; saved mixed lists by numeric ID | Global `tmdb_token` or source `token`; private lists require an owner-authorized user token |

Private TMDB authentication is described in [TMDB's list documentation](https://developer.themoviedb.org/v4/reference/list-details).
Excludarr does not run interactive OAuth login, renew tokens or discover all your
saved lists. Supply the tokens and IDs yourself. Renew tokens outside Excludarr.
Even a source needing no token, such as StevenLu, may need `tmdb_token` to enrich
missing metadata or export IDs.

Charts default to the first **100** titles, configurable with `limit: 1..1000`.
The limit applies **before** filters, so the outgoing feed may be shorter. TMDB
Trending supports `time_window: day|week`, default week. Saved lists and watchlists
fetch all pages. Merged sources are deduplicated by identity, keeping source order.

List filters support the existing `all`, `any`, `not`, `unless`, `year`, `genre`,
`rating` (source `tmdb`), series `status` and `streaming` conditions. Library
size/tags/monitoring, playback and request conditions are unavailable for external
list items. Series streaming requires coverage of every non-special episode
returned by JustWatch; it cannot guarantee coverage of missing catalog episodes.

## Troubleshooting

| Symptom | Check or next step |
| --- | --- |
| HTTP 401 | Use `list_proxy.api_key` in `?apikey=…`; this is not the TMDB token. URL-encode it if needed. |
| HTTP 404 | Use `/lists/NAME`, with the exact name under `list_proxy.lists`. |
| HTTP 503 | Run `lists status` then `lists refresh NAME`; check age, last error, matching config and database. |
| Connection refused | Keep `serve` running; check bind address, host/container routing and port. `refresh` does not start a server. |
| Included despite missing streaming data | Default `on_unknown: include`; inspect the reason or choose `exclude`. |
| `Missing tvdb_id` / `Missing imdb_id` | That title cannot be exported; other valid titles still publish. Check its external IDs in TMDB. |
| Source refresh error | The message names the source, outgoing list, step, and title/IDs when available. Retry only that list, e.g. `lists preview series`. |
| `environment variable … is not set` | Export the variable locally or configure Compose's `.env`; Excludarr does not read `.env` itself. |

The standard-library HTTP server is intended for a trusted private network. Keep
the feed key/URLs secret. When using a reverse proxy, terminate HTTPS there and
omit query strings from its access logs. Excludarr suppresses its own HTTP access
logs containing feed credentials.
