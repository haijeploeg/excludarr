# List Proxy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Serve filtered Radarr/Sonarr lists from Trakt, StevenLu, Plex Watchlist and TMDB, including Popular, Trending and saved lists.

**Architecture:** Source adapters normalize independent list items; metadata enrichment and the existing three-valued condition tree produce included/excluded decisions. CLI refresh publishes atomic SQLite snapshots. A separate read-only HTTP process serves authenticated snapshots without upstream calls.

**Tech Stack:** Existing Python >=3.12, Typer, Rich, httpx, Pydantic, SQLAlchemy/Alembic, pytest/respx; standard-library HTTP server. No added dependency.

**Spec:** `docs/superpowers/specs/2026-11-11-list-proxy-design.md` (approved 2026-11-11).

## Global Constraints

- Never commit, push, create PRs or release without explicit user instruction.
- English artifacts and terminal copy; Dutch conversation.
- Preserve existing CLI/config behavior and library action semantics.
- Charts: default limit 100, maximum 1000, applied before filtering; saved lists/watchlists fetch all pages.
- Snapshot lifetime six hours, refresh hourly via existing cron; server restart after config edits.
- Four sources are required; no discover builder, OAuth login UI, token renewal or friends' Plex watchlists.
- Missing facts are unknown. Unknown exclusion decisions follow per-list on_unknown: include|exclude, default include.
- Never include credentials in report data, errors, logs or public feeds.

## File Structure

- `src/excludarr/list_config.py`: source discriminated unions, outgoing list/proxy models and validation; existing `config.py` owns cross-checks with profile/integrations.
- `src/excludarr/lists/items.py`: independent optional-metadata `ListItem`; no imports from config or adapters.
- `src/excludarr/clients/list_sources.py`: four source adapters using the existing `HttpClient` pattern.
- `src/excludarr/clients/tmdb.py`: metadata/identity enrichment shared by all sources.
- `src/excludarr/lists/filtering.py`: safe item evaluation with shared parser/evidence.
- `src/excludarr/lists/service.py`: acquisition, normalization, filtering, reporting and atomic publication.
- `src/excludarr/lists/server.py`: authenticated snapshot-only HTTP handler.
- Add minimal `lists/__init__.py`; no public re-export layer.
- Existing `conditions.py`, `facts.py`, `storage/{models,repo}.py`, migrations, `cli.py`, README and examples change only where needed.
- Tests mirror these units; synthetic sanitized upstream fixtures live in `tests/fixtures/lists/`.

## Review Focus

1. A later source page fails: old snapshot survives without extending its timestamp (Tasks 2, 5).
2. Missing show metadata/episode coverage: never invent false/zero facts or vacuous streaming matches (Task 3).
3. An alias with conflicting IDs: never merge distinct titles through deduplication (Tasks 2, 5).
4. Credential/filter edits while serving: restart and fingerprint invalidation prevent serving an incompatible snapshot (Tasks 4, 6).
5. Expired/absent snapshot versus genuinely empty feed: HTTP 503 versus HTTP 200 `[]` (Tasks 4, 6).

---

### Task 1: Configuration and independent list items

**Files:** Create `list_config.py`, `lists/__init__.py`, `lists/items.py`; modify `config.py`; test `tests/test_list_config.py`.

**Interfaces:**
- `ListItem` dataclass: `title: str`, `kind: Literal['movie','series']`; optional `year`, `tmdb_id`, `imdb_id`, `tvdb_id`, `genres`, `ratings`, `ended`, all defaulting to None. Genres use frozenset, ratings use dict keyed by source. No library flags or arr IDs.
- `SourceConfig`: discriminated union with `type` = trakt/stevenlu/plex_watchlist/tmdb. Trakt/TMDB require `mode`; chart `media_type` = movie/series. Trakt list mode requires user/list slug or ID; TMDB list mode requires integer list_id. Private tokens are explicit Pydantic secret values. Plex requires token; StevenLu optionally accepts HTTP(S) URL.
- `ProxyList`: `target`, nonempty `sources`, parsed `when`, `unless` default `[]`.
- `ListProxyConfig`: nonempty secret `api_key`, optional secret `tmdb_token`, sources/lists mappings. `Config.list_proxy: ListProxyConfig | None = None`.

- [x] Write tests for every mode and rejection, with assertions equivalent to:
  ```python
  assert valid_proxy.sources['chart'].limit == 100
  assert valid_proxy.sources['weekly'].time_window == 'week'
  assert ListItem(title='Example', kind='series').year is None
  assert legacy_config.list_proxy is None
  ```
  Parametrize invalid 0/1001/bool limits, irrelevant mode fields, malformed URLs, unsafe slugs, duplicate YAML mapping keys in proxy config, unknown source references, empty sources, unsupported conditions and StevenLu→Sonarr. Config loaders must reject duplicate proxy names before YAML overwrites them; preserve existing secret-safe YAML error handling.
- [x] Run `.venv/bin/pytest -q tests/test_list_config.py` and confirm RED for absent models.
- [x] Implement models/validation, preserving original ${VAR} substitution. Validate `my_providers` and available rating sources; allow year/genre/rating/status/streaming only, movie/series levels. Distinguish absent metadata from known empty metadata. Do not put secrets into ValidationError output.
- [x] Run the new tests plus `tests/test_config.py tests/test_example_config.py`; require PASS.

### Task 2: Four source clients and TMDB enrichment

**Files:** Create `clients/list_sources.py`, `clients/tmdb.py`, `tests/clients/test_list_sources.py`, `tests/clients/test_tmdb.py`, sanitized fixtures.

**Interfaces:**
- `fetch_source(source: SourceConfig, *, tmdb_token: str | None) -> list[ListItem]` dispatches to clients; returns normalized items in upstream order, raises `IntegrationError` for invalid/failed acquisition.
- `TmdbClient(token: str, http: HttpClient | None = None)`; `enrich(item: ListItem, fields: frozenset[str]) -> ListItem`. Return optional missing facts; malformed identities raise IntegrationError. Fields name item attributes.
- Use supplied IDs to resolve TMDB external IDs; never search only by title. Resolve target export ID even when no metadata filter needs enrichment. Do not fetch unrelated metadata.

- [x] Verify exact source contracts against primary docs/current arr adapters before coding; record URLs alongside fixtures. Include Trakt Popular (bare items) versus Trending (nested movie/show), saved list/watchlist wrappers, API version/client headers, TMDB v3 charts/v4 lists, Plex discovery Watchlist JSON pagination and GUID resolution, StevenLu title/imdb_id. Verify rate limits and use source pacing where required. Synthetic fixtures must reflect verified shapes.
- [x] Write respx tests with assertions:
  ```python
  assert [item.imdb_id for item in result] == ['tt0000001', 'tt0000002']
  assert len(chart_result) == 100
  assert enriched.tvdb_id == 12345
  assert enriched.ratings.get('imdb') is None
  ```
  Cases: both media types, each source/mode, public/private authorization, all saved pages, deliberate chart cutoff, empty list, later-page 500, repeated page/non-progress pagination, malformed wrapper/ID, negative/bool IDs, contradictory IDs, missing metadata, absent export ID and no TMDB credential. Assert no token appears in exception text/log capture.
- [x] Run the new client tests; require RED, then implement minimal adapters on HttpClient with dependency injection for fixtures. URL-encode path identifiers; never forward credentials across arbitrary URLs or redirects.
- [x] Run `.venv/bin/pytest -q tests/clients/test_list_sources.py tests/clients/test_tmdb.py tests/clients/test_http.py`; require PASS.

### Task 3: Three-valued filtering without library defaults

**Files:** Create `lists/filtering.py`, `tests/test_list_filtering.py`; modify `conditions.py` and `facts.py` only as necessary; extend `tests/test_conditions.py`, `tests/test_facts_streaming.py`.

**Interfaces:**
- `ListDecision` dataclass: `item: ListItem`, `status: Literal['included','excluded']`, `evidence: list[Evidence]`.
- `decide(item: ListItem, rule: ProxyList, ctx: Context) -> ListDecision`.
- `Context.list_streaming(item: ListItem) -> list[Avail] | None`: reuse matching/offers/cache/breaker, take non-special JustWatch returned episode keys for series. No modification of the library streaming episode-set semantics.

- [x] Write tests asserting:
  ```python
  assert decision_for_unknown_year.status == 'excluded'
  assert decision_for_known_nonmatch.status == 'included'
  assert decision_for_streaming_match.status == 'excluded'
  assert decision_with_true_unless.status == 'included'
  assert decision_for_empty_show_episodes.status == 'excluded'
  ```
  Cover `all`/`any`/`not`, unknown unless, independent decisive branches, known empty genre versus absent genre, partial show coverage and specials, provider resolution failure, missing rating source and breaker behavior.
- [x] Run `.venv/bin/pytest -q tests/test_list_filtering.py`; confirm RED.
- [x] Implement via the existing evaluator/evidence path. Introduce only the context/item hook necessary to avoid library defaults; update affected callers and type hints together. Do not copy the boolean evaluator or reinterpret unknown as false. Preserve current library ratings and JustWatch cache compatibility.
- [x] Run new tests plus `tests/test_conditions.py tests/test_facts_streaming.py tests/test_engine.py`; require PASS.

### Task 4: Snapshot persistence and validity

**Files:** Modify `storage/models.py`, `storage/repo.py`; create next sequential Alembic revision after current head; create `tests/test_list_snapshots.py`.

**Interfaces:**
- `ListSnapshot` model: slug primary key, JSON payload/report, fingerprint, successful_at UTC, last_attempt_at UTC, optional last_error. Failed attempts can exist before any success; payload/report/fingerprint/successful_at nullable together.
- `SnapshotEntry` dataclass mirrors those fields.
- `Repo.list_snapshot(slug: str) -> SnapshotEntry | None`.
- `Repo.list_publish(slug: str, payload: list[dict], report: dict, fingerprint: str, at: datetime) -> None`.
- `Repo.list_failure(slug: str, error: str, at: datetime) -> None`.
- `fingerprint(config: Config, slug: str) -> str` in `lists/service.py`: canonical relevant source/list/profile config; keyed credential digests use feed API key as HMAC key, never persist raw secrets. Include output contract revision constant. Snapshot validity requires matching fingerprint and `0 <= age < six hours`.

- [x] Write database tests asserting failed publication leaves old payload/fingerprint/successful_at intact, records attempt/error, and a later success clears failure; UTC survives roundtrip; expiry at exactly six hours is invalid; credential/filter edits change fingerprint but unchanged config does not. Assert serialized rows contain no literal credentials. Upgrade an existing database with queue/history/cache rows and assert they survive.
- [x] Run `.venv/bin/pytest -q tests/test_list_snapshots.py`; confirm RED.
- [x] Implement migration and repo methods using existing UTCDateTime and transaction/session pattern. Migrate once on Repo startup; no migration per HTTP request.
- [x] Run new tests plus `tests/test_repo.py`; require PASS.

### Task 5: Refresh service, reports and CLI

**Files:** Create `lists/service.py`, `tests/test_list_service.py`, `tests/test_list_commands.py`; modify `cli.py`, use existing reporting/output utilities.

**Interfaces:**
- `build_list(config: Config, slug: str, repo: Repo, now: datetime) -> dict`: keys `name`, `payload`, `items`, `summary`; items contain sanitized IDs/title/decision/evidence; summary has included/excluded counts.
- `refresh_list(config: Config, slug: str, repo: Repo, now: datetime, *, publish: bool = True) -> dict` computes, optionally atomically publishes, records sanitized failure only when publishing. Exceptions remain IntegrationError/ConfigError.
- CLI: `lists refresh [NAME]`, `lists preview NAME`, `lists status`, each supporting existing `-o/--output`. Refresh all lists continues independent lists after failure, emits one aggregate report and returns nonzero for any failure/unknown excluded title. Preview does not mutate snapshots or failure status.

- [x] Write service/CLI tests asserting:
  ```python
  assert document['summary']['excluded'] == 1
  assert result.exit_code != 0  # unknown excluded title, sanitized report still emitted
  assert repo.list_snapshot('movies').payload == expected_previous_payload
  assert len(json.loads(result.stdout)['items']) == 2  # two list reports, one document
  ```
  Cover first-source order, cross-source dedup after enrichment, conflicts, later-page failure with no partial publish, successful empty list, invalid list name, JSON/YAML stderr separation, preview unchanged snapshots, status with no upstream calls and refresh-all partial success. Assert no arr/Plex-library mutation endpoints are called.
- [x] Run new service/CLI tests; confirm RED.
- [x] Implement pipeline using Tasks 1–4. Fetch only configured sources, enrich required fields, deduplicate, evaluate, project target payload. Reuse document/serialize/print_rows and the CLI error boundary; no new report framework. Refresh failures expose source name and sanitized reason, never upstream URL with credentials.
- [x] Run `.venv/bin/pytest -q tests/test_list_service.py tests/test_list_commands.py tests/test_cli_commands.py`; require PASS.

### Task 6: Authenticated HTTP snapshot server

**Files:** Create `lists/server.py`, `tests/test_list_server.py`; modify `cli.py`.

**Interfaces:**
- `make_server(config: Config, repo: Repo, host: str, port: int) -> HTTPServer`; handler closes over fixed config/repo, owns no shared Session. Tests bind loopback port 0 and shut down/join server threads.
- `serve --host 127.0.0.1 --port 8989`; clean shutdown on keyboard interrupt, bind errors become concise CLI errors. No worker/scheduler logic.

- [x] Write local HTTP tests asserting:
  ```python
  assert unauthorized.status_code == 401
  assert expired.status_code == 503
  assert empty.status_code == 200 and empty.json() == []
  assert movies.json() == [{'title': 'Example', 'imdb_id': 'tt0000001'}]
  assert series.json() == [{'title': 'Example', 'tvdbId': 12345}]
  ```
  Test wrong/missing/duplicate apikey, Unicode key handling, unknown list after auth (404), POST (405), malformed route, future/expired timestamps, config mismatch, credential rotation after server restart, correct JSON headers/length, concurrent refresh/read and no upstream call. Assert query tokens absent from all logs, including errors. Respx rejects unexpected network calls.
- [x] Run server tests; confirm RED.
- [x] Implement exact GET route, authenticate first using constant-time byte comparison, read snapshot with per-request session and return only payload. No exception detail in HTTP errors. Ignore client-provided paths as filesystem/upstream locations. Use JSON errors for 401/404/405/503.
- [x] Run `.venv/bin/pytest -q tests/test_list_server.py tests/test_list_commands.py`; require PASS.

### Task 7: Deployment examples and complete verification

**Files:** Modify `README.md`, `.examples/excludarr-example.yml`, `.examples/docker-compose-example.yml`; create `.examples/list-proxy-crontab`; extend `tests/test_example_config.py`.

- [x] Add English config examples for all four sources and Trakt/TMDB popular/trending/saved modes, private-token requirements and env substitution. Existing sample must validate without requiring new secrets when proxy is disabled; keep an opt-in separate YAML example if needed.
- [x] Add two opt-in compose services sharing config/SQLite volume: `serve --host 0.0.0.0` and cron refresh hourly. Reuse image/entrypoint; do not alter default cron behavior. Mount selected crontab and document shared UID/permissions. Show initial refresh and restart requirements, feed URLs and Radarr StevenLu Custom/Sonarr Custom List setup.
- [x] Document chart limits before filtering, unknown-result exit status, series catalog coverage, six-hour expiry/lag, private deployment boundary and manual token renewal. No claims of real-service verification.
- [x] Validate example config(s) in tests and run:
  ```bash
  .venv/bin/pytest -q
  .venv/bin/ruff format --check src tests
  .venv/bin/ruff check src tests
  .venv/bin/excludarr --config .examples/excludarr-example.yml config validate
  git diff --check
  ```
  Require all PASS. Build Docker and smoke `--version` and `serve --help` if daemon is available; otherwise record that check as skipped. No live imports/deletions.

## Self-review

Coverage: source scope/config → Tasks 1–2; filter semantics → Task 3; atomicity,
expiry and credential invalidation → Tasks 4–6; all CLI/HTTP/deployment contracts →
Tasks 5–7. Each interface is defined before use. Five review-focus failures have
owning tests. Implementation bodies are intentionally left to the implementer.
No product changes or commits are included in this planning step.

## Implementation record

Implemented on `codex/list-proxy` without commits. Independent read-only review
found no remaining important findings after the TVDB-only streaming enrichment
fix and later-page HTTP failure/direct and bridge-alias regression tests.

Implementation rulings:
- Use one source model with mode-specific field validation instead of separate
  union models; the same mode constraints are enforced with fewer classes.
- Reject duplicate YAML mapping keys while preserving normal merge-key overrides.
- ListItem uses the shared Context.streaming path directly; library behavior is
  unchanged and no trivial forwarding method was added.
- Feed refresh forces JustWatch lookups to avoid inheriting the library's one-day
  offer cache. This costs additional upstream requests per hourly refresh.
- Missing optional metadata without a TMDB token follows on_unknown; a missing required
  export ID fails refresh. Configure TMDB enrichment for complete coverage.
- Sanitized fixtures remain inline with assertions; primary contract references
  are in tests/fixtures/lists/README.md.
- Docker has a dedicated opt-in Compose example rather than changing the default
  library cron deployment. No package/version/release modifications were needed.
- CLI config validation also checks outgoing-list providers and describes filters.

Verification uses mocked source HTTP and live localhost serving. Public JustWatch
provider-name validation and a Docker build/version/help smoke test succeeded.
Final verification: 360 tests passed; Ruff check/format and git diff --check clean.

Live private source credentials, actual Radarr/Sonarr imports and a complete
container cron cycle remain unverified. No library actions were executed.

### Post-test user revision: unknown decisions

The user requested configurable uncertainty handling after inspecting real output.
`ProxyList.on_unknown` now defaults to `include`; `exclude` opts into the original
behavior. Decisions preserve `unknown: true` in structured reports and explain
missing data in the table. Existing three-valued tests explicitly select `exclude`
where they exercise withholding. Default/explicit include, explicit exclude, invalid
policy, feed publication, CLI exit codes and table evidence are regression-tested.
Changing the policy invalidates snapshots through the existing fingerprint;
restart the server and refresh lists after changing it. Unknown decisions may
therefore import titles that are actually on streaming services, as intended by
the user's preferred default. Source/identity failures remain refresh failures.

### Naming alignment

User requested `on_unknown: include|exclude`, replacing `hold`. There are exactly
two decision values and summary counters: included/excluded. Missing facts remain
`unknown: true`, with an explanatory table reason. Unknown exclusion retains its
nonzero CLI exit status (`status: incomplete`); it is not a third decision.
Old `on_unknown: hold` is rejected so configuration errors are explicit.

### User revision: isolate missing export IDs

A missing IMDb/TVDB export ID after enrichment excludes only that title and adds
an explicit `reason` to its report row. This is a known export limitation, not an
unknown filter decision; `on_unknown` does not override it and refresh succeeds.
The remaining valid titles publish atomically. Conflicting identities and source
acquisition failures retain their failure behavior. Real mixed valid/missing-ID
fixtures verify both Radarr and Sonarr payloads and persisted snapshots.
