# List proxy

Status: approved by the user on 2026-11-11. Project 2, following the library rule engine.

## Intent and established decisions

Excludarr fetches source lists and serves filtered Custom Lists to Radarr and
Sonarr. Titles matching an exclusion filter never enter the outgoing feed.
The user chose a true proxy rather than periodically creating import exclusions.
The four agreed sources are Trakt, StevenLu, Plex Watchlist and TMDB.
Trakt and TMDB must support Popular and Trending as well as the user's saved
lists (user clarification, 2026-11-11).
Python, Docker and continued standalone CLI use remain requirements. The web UI,
Helm chart and general-purpose daemon belong to project 3.

## Approach

The true proxy is the selected approach. A Radarr/Sonarr import-exclusion worker
was rejected because it races list imports. A live upstream fetch on every HTTP
request is possible but makes imports depend on JustWatch latency. My proposal
is an explicit CLI refresh plus a small HTTP process serving persisted snapshots.
Existing cron mode can refresh feeds; no scheduler is added to the HTTP process.
Deploy two processes/containers sharing the config and SQLite volume: one serves,
the other uses cron to refresh hourly. The current entrypoint cannot run both
modes in one container. Restart the server after configuration or credential
changes; its in-memory configuration is fixed for its lifetime.

Source names and Popular/Trending/saved-list support are user decisions. Other
details below are implementation proposals.

## Source scope

- Trakt: Popular and Trending movie/show charts, named saved user lists by
  owner/list ID or slug, and the authenticated user's watchlist, including private
  lists with a supplied access token. Configure client ID and optional access
  token; interactive OAuth and automatic token renewal are outside this version.
- StevenLu: the public movie feed, with an optional administrator-configured
  compatible HTTP(S) URL. It is movie-only.
- Plex Watchlist: the watchlist of the account identified by a configured Plex
  token, including movies and shows. This is Plex's online watchlist, separate
  from the existing local Plex library integration. No friends' watchlists.
- TMDB: Popular movie/TV charts, Trending movie/TV charts (day or week, default
  week), and saved named lists by list ID. Use v3 chart endpoints and the v4 list
  endpoint for mixed movie/TV lists. Public lists use the configured read token;
  private lists require an owner-authorized user token. No discover-query builder.

Source `mode` selects `popular`, `trending`, `list` or (Trakt only) `watchlist`.
Trakt/TMDB require an explicit mode; charts also require `media_type` (`movie` or
`series`). StevenLu and Plex Watchlist have a single mode. Reject fields irrelevant
to a mode. Users configure saved lists explicitly by ID/slug; automatic account
list discovery is not required. Charts use a positive `limit` (default 100, maximum
1000) and fetch as many pages as needed to reach it or exhaust the source. The
limit applies before filtering, so the outgoing feed may contain fewer titles.
Saved lists and watchlists fetch all pages; a chart limit is deliberate, never a
silent pagination truncation.

Follow pagination to the configured chart limit or end of list; never silently
publish a truncated list after an API failure.
Validate response shapes and IDs. Treat a malformed source item as a refresh failure, with a useful source/item
error. A title missing its required export ID after enrichment is individually
excluded with an explicit reason; publish the other valid titles. A well-formed item
of the other media kind is ignored. No title-only identity matching.

## Configuration and identity

Add optional `list_proxy` to the existing YAML. It contains a required nonempty
secret `api_key`, named `sources`, and named `lists`. Each outgoing list has a
`target` (radarr or sonarr), source names, `when`, optional `unless` conditions
and `on_unknown: include|exclude` (default include).
Reject unknown fields, duplicate names, unknown references, invalid slugs and
unsupported target/source combinations. Existing configurations remain valid.

Use a separate list item carrying title, kind, year, TMDB/IMDb/TVDB IDs and optional
metadata. Do not let the defaults of `MediaItem` invent library facts such as
monitored=true or size=0. Enrich missing export IDs and requested metadata through
TMDB. Require its read token when configured sources cannot supply these IDs.
Radarr exports require IMDb IDs; Sonarr exports require TVDB IDs for compatibility.
Deduplicate after enrichment using target ID, preserving first source order;
conflicting IDs fail the refresh rather than mixing two titles.

Example (field names are the proposed public contract):

```yaml
list_proxy:
  api_key: ${LIST_PROXY_API_KEY}
  tmdb_token: ${TMDB_READ_TOKEN}
  sources:
    popular:
      type: stevenlu
    favourites:
      type: tmdb
      mode: list
      list_id: 12345
    trending_series:
      type: trakt
      mode: trending
      media_type: series
      client_id: ${TRAKT_CLIENT_ID}
      limit: 100
  lists:
    movies:
      target: radarr
      sources: [popular, favourites]
      when:
        streaming: my_providers
```

The optional `list_proxy` section does not remove the existing requirement for an
arr integration in this version. It never calls arr write endpoints.

## Filtering semantics

Reuse condition parsing, `all`/`any`/`not`, three-valued evaluation and evidence.
For each item, exclude only when `when` is true and every `unless` is false.
Include when exclusion is definitively false. On an unknown final decision, use
`on_unknown: include|exclude`, default include (user revision after testing). Always
report the unknown result; included unknown titles have `unknown: true`. With
`exclude`, omit them from the feed and return a nonzero CLI exit code. Independent
boolean branches retain the current three-valued behavior. Source acquisition
failures still fail refresh, preserving the previous snapshot. Missing required
export IDs exclude the affected title only, regardless of on_unknown.

Initially allow year, genre, rating, series status and streaming conditions. Reject
library-only, playback and request conditions during config validation. Missing
metadata is unknown, never zero or an empty collection. Retain rating source names;
TMDB ratings cannot masquerade as IMDb or Sonarr ratings.

Streaming defaults to the existing profile provider selection and monetization
semantics. Reuse JustWatch matching, offer cache and circuit breaker. A movie uses
its movie offers. For a series, use the non-special episode set returned by
JustWatch and require every returned episode to meet the existing streaming
condition. An empty or unavailable episode set is unknown. This is explicitly
coverage of the returned JustWatch catalog, not a guarantee that unaired episodes
or episodes missing from that catalog are available. Keep library series behavior
unchanged; never treat an empty local episode list as complete coverage.

## CLI, persistence and HTTP

- `excludarr lists refresh [NAME]`: fetch, enrich, filter and persist snapshots;
  optional name selects one outgoing list. Existing JSON/YAML/table reporting
  conventions apply, with included/excluded decisions and evidence.
- `excludarr lists preview NAME`: compute the same result without replacing the
  published snapshot. Normal lookup caching is permitted.
- `excludarr lists status`: local snapshot age, counts and last refresh outcome.
- `excludarr serve --host 127.0.0.1 --port 8989`: a read-only HTTP process, using
  Python's standard HTTP server for a trusted private deployment. No dependency
  or general API framework. Docker users explicitly bind to `0.0.0.0`.
- `GET /lists/{slug}?apikey=...`: JSON array, Radarr entries contain `title` and
  `imdb_id`; Sonarr entries contain `title` and `tvdbId`. Correct content type and
  content length; unsupported methods fail. Authenticate before revealing list
  existence, with constant-time comparison. Suppress credential-bearing access
  logs. No upstream requests or client-selected upstream URLs in handlers.
- Add SQLite snapshot storage through an Alembic migration. Persist payload,
  sanitized decision report, config fingerprint and successful refresh timestamp.
  Persist failure status independently. Never store source or feed credentials in
  reports, fingerprints or messages. Use a nonsecret config fingerprint; invalidate
  snapshots on config edits and compare a secret-keyed digest for credential changes.
- A snapshot expires after six hours. Return HTTP 503 for absent, expired or
  configuration-mismatched snapshots, rather than a successful empty list.
  A successful genuinely empty source/filter result is HTTP 200 with `[]`.
  Cached decisions can lag streaming/source changes until the next successful
  refresh; six hours bounds accepted snapshot age, not real-time availability.

Publication is atomic per outgoing list, after every source page and enrichment
succeeds. Transport, authentication, pagination or malformed-source failures
preserve the preceding snapshot. A valid snapshot can contain unknown excluded items; reports
must expose them and the CLI returns nonzero when any unknown item is excluded. A refresh
failure returns nonzero; failed attempts do not extend snapshot lifetime. Each
HTTP request uses its own database session; CLI refresh and server reads can
coexist. Refresh errors and credentials never enter the public JSON feed.

## Delivery boundaries

Changes reach config validation, dedicated source clients on `HttpClient`, proxy
item/filter code, shared condition support where necessary, snapshot storage and
migration, CLI commands, HTTP serving, example config/compose and English README.
The existing library action executor, queue, rescue and history behavior stays
independent. No commits or release changes are part of this work.

Verification uses pytest/respx and fixtures for all four sources, Popular/Trending
movie/show response differences, saved lists, chart limits and pagination,
ID enrichment and deduplication, missing metadata, partial series coverage,
three-valued filters, credential redaction, invalid configuration, atomic publish,
snapshot expiry/config invalidation, CLI reports and authenticated HTTP responses.
Run the full existing suite, Ruff and example config validation. Real service
credentials and live arr imports require a later user-side smoke test.

## Protocol references

- Radarr StevenLu parser consumes `title` and `imdb_id`:
  https://github.com/Radarr/Radarr/blob/develop/src/NzbDrone.Core/ImportLists/StevenLu/StevenLuParser.cs
- Sonarr Custom import deserializes a JSON array and maps provider IDs:
  https://github.com/Sonarr/Sonarr/blob/develop/src/NzbDrone.Core/ImportLists/Custom/CustomImportProxy.cs
  https://github.com/Sonarr/Sonarr/blob/develop/src/NzbDrone.Core/ImportLists/Custom/CustomImport.cs

Exact upstream endpoint/authentication contracts for the four source clients must
be checked against their primary documentation/source before implementation.

- TMDB Trending: https://developer.themoviedb.org/reference/trending-all
- TMDB saved lists: https://developer.themoviedb.org/v4/reference/list-details
- Trakt primary API documentation: https://developer.trakt.tv/
