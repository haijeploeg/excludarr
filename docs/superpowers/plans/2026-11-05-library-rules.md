# Excludarr v2 — Library Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the v1 codebase with a rule engine that evaluates user-defined YAML rules against Radarr/Sonarr items. Conditions come from Radarr/Sonarr, JustWatch, Tautulli+Plex and Seerr. Rules take actions with preview mode, a grace queue and history, all driven from a Typer CLI.

**Architecture:**
- One core package under `src/excludarr/`: config models, HTTP clients per integration, an item model, "facts" (lazy, cached lookups of external data per item), conditions with three-valued evaluation, actions with their side effects, and an engine.
- The CLI is a thin layer over the engine.
- State lives in SQLite through SQLAlchemy and Alembic.

**Tech Stack:** Python ≥ 3.12 · Typer · Rich · httpx · Pydantic v2 · PyYAML · SQLAlchemy 2 · Alembic · pytest · respx · ruff.

**Spec:** `docs/superpowers/specs/2026-11-05-library-rules-design.md` (read it before starting any task).

## Global Constraints

- Python `>=3.12`. Packaging: PEP 621 `pyproject.toml` with the hatchling backend and a src layout. Version `2.0.0`.
- **Do not commit.** The user's standing rule is that agents never run `git commit`, create branches or push. Each task ends with a checkpoint: run the tests, list the changed files and stop. The user commits.
- All code, comments, docs and messages are in English.
- No pyarr, no python-plexapi, no TMDB client. Every integration talks HTTP through `clients/http.py` (httpx, sync).
- Match items on IDs (TMDB/IMDB/TVDB) only. Titles are for display.
- Three-valued logic: a condition returns `True`, `False` or `None` (unknown). A rule acts only when `when` is `True` **and** `unless` is `False`. Unknown never leads to an action.
- New rules default to `preview: true`, and the default `grace_period` is `0`. For Sonarr rules the default `level` is `season`.
- Season 0 (specials) is not an item at season or episode level. ponytail: specials are ignored; add them when someone asks.
- Format and lint: `ruff format` + `ruff check`, line length 100.
- Tests never hit the network. Use respx for httpx, plus fakes for the facts and clients.

## Review Focus

1. **Integration down mid-run** (Tautulli or Seerr times out). Expected: the conditions that depend on it become unknown for the whole run, a warning is printed, and nothing is deleted because of it. The test lives in Task 8 (`test_watch_unknown_when_tautulli_fails`).
2. **Title not found on JustWatch, or the show is matched but a season is missing from the JustWatch data.** Expected: an unmatched title makes streaming unknown. A matched show with a missing season makes that season `False`, never `True`. Tests in Task 6.
3. **A rule renamed or removed while items are in its grace queue.** Expected: the orphaned queue rows are dropped and removed from the Leaving Soon collection on the next run, and nothing is executed. Test in Task 12 (`test_orphaned_queue_rows_dropped`).
4. **A main action fails halfway** (the Radarr delete returns 500). Expected: history records `ok=False`, the item stays queued for a retry, and side effects are not attempted. A side-effect failure is recorded but does not undo the main action. Tests in Task 11.
5. **An item matched by two rules in the same run** (one deletes the series, a later one targets one of its seasons). Expected: the later rule skips anything already removed in this run. Test in Task 12 (`test_later_rule_skips_removed_items`).

---

## File Structure

```
pyproject.toml                       # replaces setup.py/setup.cfg/requirements*.txt/poetry.lock/MANIFEST.in
src/excludarr/__init__.py            # __version__ = "2.0.0"
src/excludarr/cli.py                 # Typer app; all commands
src/excludarr/config.py              # Pydantic config + rule models, load/find config, durations, sizes
src/excludarr/conditions.py          # condition tree, parsing, describe(), evaluate()
src/excludarr/items.py               # MediaItem, EpisodeRef, builders for Radarr/Sonarr
src/excludarr/facts.py               # Context: streaming/watch/request/plex facts, caching, prefetch
src/excludarr/actions.py             # execute(rule, item, ctx) + side effects
src/excludarr/engine.py              # evaluate_rule(), run()
src/excludarr/output.py              # Rich tables
src/excludarr/clients/http.py        # HttpClient (retries, backoff, timeouts), IntegrationError
src/excludarr/clients/{radarr,sonarr,justwatch,tautulli,plex,seerr}.py
src/excludarr/clients/justwatch_queries.py   # ported from excludarr/modules/justwatch/queries.py
src/excludarr/storage/{__init__,models,repo}.py
src/excludarr/storage/migrations/    # alembic env.py + versions/0001_initial.py
tests/...                            # mirrors src
Dockerfile, entrypoint.sh, .examples/excludarr-example.yml, README.md, CHANGELOG.md
```

---

### Task 1: Scaffold v2 package, remove v1

**Files:**
- Delete: `excludarr/` (old package; first copy `excludarr/modules/justwatch/queries.py` to `src/excludarr/clients/justwatch_queries.py` unchanged, and keep `excludarr/modules/justwatch/justwatch.py` open as a reference for Task 6), `setup.py`, `setup.cfg`, `requirements.txt`, `requirements-dev.txt`, `poetry.lock`, `MANIFEST.in`, `.pre-commit-config.yaml` (re-created with ruff), `BUILD-jwfix.md` / `Dockerfile.jwfix` if present.
- Create: `pyproject.toml`, `src/excludarr/__init__.py`, `src/excludarr/cli.py`, `tests/test_cli.py`, `.pre-commit-config.yaml`.

**Interfaces:**
- Produces: `excludarr.cli:app` (a Typer app) and the console script `excludarr = "excludarr.cli:main"`. `main()` calls `app()`.
- Global options on the app callback: `--config PATH` (env `EXCLUDARR_CONFIG`), `--debug`, `--version`. They are stored in a module-level `state` dict that later tasks read.

- [ ] **Step 1:** Write `pyproject.toml`.
  - Dependencies: `typer>=0.12`, `rich>=13`, `httpx[http2]>=0.27`, `pydantic>=2.7`, `pyyaml>=6`, `sqlalchemy>=2.0`, `alembic>=1.13`.
  - Optional `dev` extras: `pytest>=8`, `respx>=0.21`, `ruff>=0.6`.
  - `[tool.pytest.ini_options] testpaths=["tests"]`; `[tool.ruff] line-length=100`.
  - Include the package data `storage/migrations/**`.
- [ ] **Step 2: Failing test** in `tests/test_cli.py`:
```python
from typer.testing import CliRunner
from excludarr.cli import app

def test_version():
    r = CliRunner().invoke(app, ["--version"])
    assert r.exit_code == 0 and "2.0.0" in r.stdout
```
- [ ] **Step 3:** `python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]' && .venv/bin/pytest -q`. Expect FAIL: the import error.
- [ ] **Step 4:** Implement `__init__.py` and the `cli.py` callback with `--version`.
- [ ] **Step 5:** `.venv/bin/pytest -q` → PASS. `.venv/bin/ruff check src tests` → clean.
- [ ] **Step 6: Checkpoint.** List the changed files and stop. Do not commit.

---

### Task 2: Config models

**Files:** Create `src/excludarr/config.py`, `tests/test_config.py`.

**Interfaces:**
- Produces:
  - `parse_duration(s: str) -> timedelta`. Accepts `<int>(h|d|w)`, e.g. `"30d"`, `"12h"`, `"2w"`. Anything else raises `ValueError`.
  - `parse_size(s: str) -> int`. Accepts `<number>(MB|GB|TB)` and returns bytes, 1024-based.
  - `class ConfigError(Exception)`.
  - Integration models:
    - `Integration(url: str, api_key: str, verify_ssl: bool = True)`. `url` is normalized: the scheme is required (otherwise `ConfigError` with the message "url must start with http:// or https://"), and trailing slashes are stripped.
    - `PlexIntegration(url, token, verify_ssl=True, leaving_soon_collection: str = "Leaving Soon")`.
    - `Integrations(radarr, sonarr, tautulli, seerr: Integration | None, plex: PlexIntegration | None)`. At least one of radarr/sonarr must be set.
  - `Profile(locale: str = "en_US", providers: list[str] = [])`.
  - `Rule`: the fields are exactly those in spec §5.2, plus action options `delete_files: bool=False`, `import_exclusion: bool=False`, `search: bool=False`, `tag: str | None`.
    - `action: Literal["delete","delete_files","unmonitor","monitor","tag","import_exclusion"]`.
    - `level: Literal["movie","series","season","episode"]`. The default is `"movie"` for radarr and `"season"` for sonarr. `level` must be `"movie"` for radarr and must not be `"movie"` for sonarr.
    - `grace_period: timedelta` is parsed with `parse_duration`; `0`/`"0d"` → `timedelta(0)`.
    - `when` and `unless` stay raw at this point (`Any` / `list[Any]`). Task 10 swaps them for parsed conditions.
  - `Config(profile: Profile = Profile(), integrations: Integrations, rules: list[Rule] = [], database: str | None = None)`. Rule names must be unique. `action == "tag"` requires `tag`. `leaving_soon_collection: true` requires plex.
  - `find_config_path(explicit: Path | None) -> Path`. Order: explicit → `$EXCLUDARR_CONFIG` → `./excludarr.yml` → `~/.config/excludarr/excludarr.yml` → `/config/excludarr.yml` → `/etc/excludarr/excludarr.yml`. The first one that exists wins. If none exists, raise `ConfigError`.
  - `load_config(path: Path | None) -> tuple[Config, Path]`. Substitutes `${VAR}` from the environment before parsing YAML; an unset var raises `ConfigError` naming the var. A Pydantic `ValidationError` is re-raised as `ConfigError` carrying the readable message.
  - `database_url(config: Config, config_path: Path) -> str`. Returns `config.database` if set, otherwise `f"sqlite:///{config_path.parent / 'excludarr.db'}"`.

- [ ] **Step 1: Failing tests:**
```python
def test_parse_duration():
    assert parse_duration("30d") == timedelta(days=30)
    assert parse_duration("2w") == timedelta(weeks=2)
    with pytest.raises(ValueError): parse_duration("30")

def test_parse_size(): assert parse_size("1.5GB") == int(1.5 * 1024**3)

def test_url_normalized():
    assert Integration(url="http://radarr:7878/", api_key="k").url == "http://radarr:7878"

def test_url_without_scheme_rejected():   # old issue #83
    with pytest.raises(ValidationError, match="http://"): Integration(url="192.168.0.10:7878", api_key="k")

def test_sonarr_rule_defaults_to_season(minimal_cfg):  # minimal_cfg: fixture dict with radarr+sonarr
    minimal_cfg["rules"] = [{"name": "r", "target": "sonarr", "action": "unmonitor", "when": {"monitored": True}}]
    rule = Config.model_validate(minimal_cfg).rules[0]
    assert rule.level == "season" and rule.preview is True and rule.grace_period == timedelta(0)

def test_duplicate_rule_names_rejected(minimal_cfg): ...
def test_tag_action_requires_tag(minimal_cfg): ...
def test_env_substitution(tmp_path, monkeypatch): ...   # ${RADARR_KEY} → value; unset → ConfigError naming RADARR_KEY
def test_find_config_path_order(tmp_path, monkeypatch): ...
```
- [ ] **Step 2:** Run `pytest tests/test_config.py -q` → FAIL.
- [ ] **Step 3:** Implement `config.py`.
- [ ] **Step 4:** Run `pytest -q` → PASS.
- [ ] **Step 5: Checkpoint.**

---

### Task 3: Storage

**Files:** Create `src/excludarr/storage/{__init__,models,repo}.py`, `src/excludarr/storage/migrations/env.py`, `script.py.mako`, `versions/0001_initial.py`, and `tests/test_repo.py`.

**Interfaces:**
- Tables. All timestamps are timezone-aware UTC.
  - `queue(rule TEXT, item_key TEXT, title TEXT, size_bytes INT, enqueued_at, due_at, PK(rule,item_key))`
  - `exception(rule, item_key, title, created_at, PK(rule,item_key))`
  - `history(id PK, at, rule, item_key, title, action, size_freed INT, ok BOOL, detail TEXT)`
  - `cache(key TEXT PK, value JSON, expires_at)`
- `@dataclass QueueEntry(rule, item_key, title, size_bytes, enqueued_at, due_at)`, and similar `ExceptionEntry` and `HistoryEntry`.
- `class Repo(url: str)`. The constructor runs Alembic `upgrade head` programmatically, with `script_location` pointing at the package's `migrations` dir. Methods:
  - `queue_for(rule) -> dict[str, QueueEntry]`, `queue_all() -> list[QueueEntry]`, `queue_add(rule, item_key, title, size_bytes, due_at)`, `queue_remove(rule, item_key)`
  - `exceptions_for(rule) -> set[str]`, `exceptions_all() -> list[ExceptionEntry]`, `exception_add(rule, item_key, title)`, `exception_remove(rule, item_key)`
  - `history_add(rule, item_key, title, action, size_freed, ok, detail)`, `history(limit=100) -> list[HistoryEntry]` (newest first)
  - `cache_get(key) -> Any | None` (returns None when expired), `cache_set(key, value, ttl: timedelta)`

- [ ] **Step 1: Failing tests** (use `Repo(f"sqlite:///{tmp_path}/t.db")`): queue add/get/remove roundtrip; exceptions; history newest first; `test_cache_expiry` (set with `ttl=timedelta(seconds=-1)` → `cache_get` returns None); `test_migrations_idempotent` (constructing Repo twice on the same file works).
- [ ] **Step 2:** Run `pytest tests/test_repo.py -q` → FAIL.
- [ ] **Step 3:** Implement `models.py` (SQLAlchemy 2 declarative), the initial migration (matching `models.py`) and `repo.py`.
- [ ] **Step 4:** Run `pytest -q` → PASS.
- [ ] **Step 5: Checkpoint.**

---

### Task 4: HTTP base + Radarr client

**Files:** Create `src/excludarr/clients/__init__.py`, `http.py`, `radarr.py`, `tests/clients/test_http.py`, `tests/clients/test_radarr.py`.

**Interfaces:**
- `class IntegrationError(Exception)` with attributes `integration: str` and `status: int | None`. Its message contains at most 200 chars of the response body.
- `class HttpClient(name: str, base_url: str, headers: dict[str, str], verify: bool = True, timeout: float = 30.0, retries: int = 4, backoff: float = 1.0)`:
  - methods `get(path, params=None)`, `post(path, json=None, params=None)`, `put(path, json=None, params=None)`, `delete(path, params=None, json=None)`. Each returns the parsed JSON, or `None` for an empty body.
  - Retries on 429, 502, 503 and 504 and on `httpx.TransportError`. The sleep is `backoff * 2**attempt`, or the `Retry-After` value when present. Once retries are exhausted, or on any other status ≥ 400, it raises `IntegrationError`.
- `class RadarrClient(cfg: Integration, http: HttpClient | None = None)`. It sends the header `X-Api-Key` and uses the base `"{url}/api/v3"`. Methods:
  - `movies() -> list[dict]` (GET `/movie`)
  - `tags() -> dict[int, str]`; `ensure_tag(label) -> int` (POST `/tag` when the label is missing)
  - `update_movie(movie: dict) -> None` (PUT `/movie/{id}`)
  - `delete_movie(movie_id, delete_files: bool, add_exclusion: bool)` (DELETE `/movie/{id}?deleteFiles=&addImportExclusion=`)
  - `movie_files(movie_id) -> list[dict]` (GET `/moviefile?movieId=`); `delete_movie_files(file_ids: list[int])` (DELETE `/moviefile/bulk` with json `{"movieFileIds": ids}`)
  - `add_exclusion(tmdb_id, title, year)` (POST `/exclusions` with `{"tmdbId","movieTitle","movieYear"}`)
  - `search(movie_ids: list[int])` (POST `/command` with `{"name":"MoviesSearch","movieIds":ids}`)
  - `queue() -> list[dict]` (GET `/queue?pageSize=1000&includeMovie=false` → `["records"]`); `remove_queue_item(queue_id)` (DELETE `/queue/{id}?removeFromClient=true&blocklist=false`)

- [ ] **Step 1: Failing tests** (respx; `backoff=0`): `test_retries_on_503_then_succeeds`, `test_honors_retry_after`, `test_raises_integration_error_on_404` (check `.status == 404` and the integration name), `test_radarr_delete_movie_params` (asserts the query `deleteFiles=true&addImportExclusion=false`), `test_radarr_ensure_tag_creates_missing`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement. For the sleep, use `time.sleep` through a module-level function so tests can monkeypatch it.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5: Checkpoint.**

---

### Task 5: Sonarr client

**Files:** Create `src/excludarr/clients/sonarr.py`, `tests/clients/test_sonarr.py`.

**Interfaces:**
- Consumes: `HttpClient` and `Integration`.
- Produces `class SonarrClient(cfg, http=None)`, with base `"{url}/api/v3"`. Methods:
  - `series() -> list[dict]`; `episodes(series_id) -> list[dict]` (GET `/episode?seriesId=`); `episode_files(series_id) -> list[dict]` (GET `/episodefile?seriesId=`)
  - `tags() -> dict[int,str]`; `ensure_tag(label) -> int`; `update_series(series: dict)`
  - `delete_series(series_id, delete_files, add_exclusion)` (DELETE `/series/{id}?deleteFiles=&addImportListExclusion=`)
  - `delete_episode_files(file_ids)` (DELETE `/episodefile/bulk` with `{"episodeFileIds": ids}`)
  - `set_episodes_monitored(episode_ids, monitored: bool)` (PUT `/episode/monitor` with `{"episodeIds","monitored"}`)
  - `add_exclusion(tvdb_id, title)` (POST `/importlistexclusion` with `{"tvdbId","title"}`)
  - `search(series_id, season: int | None = None, episode_ids: list[int] | None = None)`. Sends the command `EpisodeSearch {"episodeIds"}` when episode_ids is given, otherwise `SeasonSearch {"seriesId","seasonNumber"}` when season is given, otherwise `SeriesSearch {"seriesId"}`.
  - `queue() -> list[dict]`; `remove_queue_item(queue_id)`

- [ ] **Step 1: Failing tests:** `test_search_picks_command` (three cases), `test_delete_series_uses_import_list_exclusion_param`, `test_set_episodes_monitored_body`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5: Checkpoint.**

---

### Task 6: JustWatch client, `providers list`, streaming facts

**Files:** Create `src/excludarr/clients/justwatch.py`, `src/excludarr/facts.py` (streaming part plus the `Context` skeleton), `tests/clients/test_justwatch.py`, `tests/test_facts_streaming.py`. Modify `src/excludarr/cli.py`.

**Interfaces:**
- `normalize_locale(locale: str) -> str`: `"nl_NL"` → `"nl_NL"`, `"nl"` → `"en_NL"`, anything else → `"en_US"`. Same behaviour as commit `62edb09`.
- `@dataclass Provider(id: int, clear_name: str, short_name: str, monetization_types: list[str])`.
- `@dataclass SearchResult(node_id: str, title: str, year: int | None, tmdb_id: int | None, imdb_id: str | None)`.
- `Avail = frozenset[tuple[int, str]]`: a set of (packageId, MONETIZATION) pairs, e.g. `(8, "FLATRATE")`.
- `class JustWatchClient(locale: str, http: HttpClient | None = None)`. POSTs go to `https://apis.justwatch.com/graphql` with the browser User-Agent from commit `62edb09`. Methods:
  - `providers() -> list[Provider]`: the `GetPackages` query from `62edb09`, with platform `WEB`.
  - `search(title, kind: Literal["MOVIE","SHOW"], first: int = 5) -> list[SearchResult]`: `SEARCH_QUERY`.
  - `movie_offers(node_id) -> Avail` and `show_offers(node_id) -> dict[tuple[int,int], Avail]`. Both use `OFFER_QUERY` with `offerFilter={"bestOnly": False}`, so every monetization type comes back. They are filtered locally later.
- In `facts.py`:
  - `class Context(config: Config, clients: Clients, repo: Repo, now: datetime)`.
  - `@dataclass Clients(radarr, sonarr, justwatch, tautulli, plex, seerr)`. Every field is optional (`None` when not configured). Add the factory `Clients.from_config(config)`.
  - `Context.provider_ids(names: list[str] | Literal["my_providers"]) -> set[int]`. Matches case-insensitively on `clear_name`; `"my_providers"` means `config.profile.providers`. An unknown name raises `ConfigError("unknown provider 'X' for locale nl_NL; see `excludarr providers list`")`. The provider list is cached in the repo cache for 7d under the key `jw:providers:{locale}`.
  - `Context.streaming(item: MediaItem) -> list[Avail] | None`. Returns one `Avail` per atomic unit: movie → `[avail]`; episode → `[avail]`; season → one per *aired* episode of that season; series → one per aired episode across seasons ≥ 1. It returns `None` when the title was not matched on JustWatch or the lookup failed. An episode missing from the JustWatch data gets `frozenset()`.
  - Matching: search by the item's base title with `kind`. Take the first result whose `tmdb_id` equals the item's `tmdb_id`, or else whose `imdb_id` matches. Cache the node_id under `jw:match:{kind}:{tmdb_id or imdb_id}` for 7d (store `""` when nothing matched) and the offers under `jw:offers:{node_id}` for 24h.
  - `Context.prefetch_streaming(items: list[MediaItem]) -> None`: warms the match and offers caches for the distinct base titles with `ThreadPoolExecutor(max_workers=4)`.
  - `MediaItem` comes from Task 9. For this task, define it in `items.py` with the fields from Task 9's Interfaces block. Task 9 only adds the builders.
- CLI: `excludarr providers list [--locale L]` prints a Rich table (id, name, short name, monetization types). The locale comes from `--locale`, otherwise from the config profile, otherwise `en_US`. No config file is required when `--locale` is given.

- [ ] **Step 1: Failing tests:**
  - `test_normalize_locale`
  - `test_providers_parses_packages` (respx JSON fixture)
  - `test_show_offers_keys_by_season_episode`
  - `test_streaming_movie_unmatched_is_none`
  - `test_streaming_season_has_one_avail_per_aired_episode` (an unaired episode, i.e. `airDateUtc` in the future, is excluded)
  - `test_streaming_missing_season_is_empty_sets_not_none` (show matched, season 3 absent from the offers → `[frozenset(), …]`)
  - `test_unknown_provider_name_raises`
  - `test_match_cached` (the second call makes no HTTP request)
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement (port from `excludarr/modules/justwatch/justwatch.py`, which you kept open from Task 1). **Step 4:** Run → PASS.
- [ ] **Step 5:** Manual smoke test (network, optional): `.venv/bin/excludarr providers list --locale nl_NL` shows Netflix with id 8.
- [ ] **Step 6: Checkpoint.**

---

### Task 7: Plex + Tautulli clients

**Files:** Create `src/excludarr/clients/plex.py`, `src/excludarr/clients/tautulli.py`, `tests/clients/test_plex.py`, `tests/clients/test_tautulli.py`.

**Interfaces:**
- `@dataclass PlexItem(rating_key: str, section_key: str, type: Literal["movie","show"])`.
- `class PlexClient(cfg: PlexIntegration, http=None)`. Sends the headers `X-Plex-Token` and `Accept: application/json`. Methods:
  - `items_by_guid() -> dict[str, PlexItem]`: for every section of type movie or show, GET `/library/sections/{key}/all?includeGuids=1`, and map each `Guid[].id` (`"tmdb://603"`, `"imdb://tt…"`, `"tvdb://81189"`) to its `PlexItem`.
  - `add_to_collection(item: PlexItem, name: str)` and `remove_from_collection(item, name)`: PUT `/library/sections/{section}/all` with `type` (1 for movie, 2 for show), `id=rating_key`, and the collection tag params in the request shape python-plexapi uses in `EditMixins`/`addCollection` and `removeCollection` (`collection[0].tag.tag=<name>` to add, `collection[].tag.tag-=<name>` to remove, `collection.locked=1`). Verify these against a real server during manual testing and note the result in the checkpoint.
  - `refresh(section_key)`: GET `/library/sections/{key}/refresh`.
- `@dataclass HistoryRow(at: datetime, user: str, friendly_name: str, rating_key: str, grandparent_rating_key: str | None, season: int | None, episode: int | None, media_type: str, watched: bool)`. `watched` is `watched_status == 1`.
- `class TautulliClient(cfg: Integration, http=None)` with `history() -> list[HistoryRow]`. It pages through `GET /api/v2?apikey=…&cmd=get_history&length=1000&start=N` until it has `recordsFiltered` rows. `season` and `episode` come from `parent_media_index` and `media_index`. Any `response.result != "success"` raises `IntegrationError`.

- [ ] **Step 1: Failing tests:** `test_items_by_guid_maps_all_guids`, `test_history_pages_until_records_filtered`, `test_history_error_result_raises`, `test_add_to_collection_params`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5: Checkpoint.**

---

### Task 8: Seerr client + watch and request facts

**Files:** Create `src/excludarr/clients/seerr.py`, `tests/clients/test_seerr.py`, `tests/test_facts_watch_requests.py`. Modify `src/excludarr/facts.py`.

**Interfaces:**
- `@dataclass SeerrRequest(id: int, media_id: int, media_type: Literal["movie","tv"], tmdb_id: int | None, tvdb_id: int | None, created_at: datetime, requested_by: frozenset[str], seasons: frozenset[int])`. `requested_by` holds the lower-cased `plexUsername`, `displayName` and `email` (whichever are present).
- `class SeerrClient(cfg: Integration, http=None)`. Header `X-Api-Key`, base `"{url}/api/v1"`. Methods:
  - `requests() -> list[SeerrRequest]`: pages `GET /request?take=100&skip=N&filter=all` until `pageInfo.pages` is reached.
  - `delete_media(media_id)`: DELETE `/media/{id}`.
  - `delete_request(request_id)`: DELETE `/request/{id}`.
- `@dataclass WatchStats(last_watched: datetime | None, play_count: int, fully_watched: bool, last_by_user: dict[str, datetime])`. The keys of `last_by_user` are lower-cased usernames *and* friendly names.
- `Context.plex_item(item) -> PlexItem | None`: looks the item up by `tmdb://`, then `imdb://`, then `tvdb://` in `items_by_guid()`. Fetched once per run.
- `Context.watch(item) -> WatchStats | None`. Returns None when Tautulli or Plex is not configured, when either call failed this run (log one warning per integration per run), or when the item is not in Plex. The history is fetched once per run.
  - Movie: rows whose `rating_key` equals the item's.
  - Series, season or episode: rows whose `grandparent_rating_key` equals the show's, filtered by season and episode.
  - `play_count` counts rows with `watched=True`.
  - `fully_watched`: for a movie, any watched row; for a series, season or episode, every aired `EpisodeRef` in the unit has a watched row.
  - `last_watched` is the max `at` over all rows, watched or partial.
- `Context.requests(item) -> list[SeerrRequest] | None`. Returns None when Seerr is not configured or failed this run. Match on `tmdb_id`, or else on `tvdb_id` for tv. Season and episode items keep only the requests whose `seasons` contain the item's season.

- [ ] **Step 1: Failing tests:**
  - `test_requests_paging`
  - `test_watch_season_rollup_most_recent_wins` (spec §5.3: episode 1 watched 90d ago, episode 2 watched 10d ago → `last_watched` is 10d ago)
  - `test_watch_fully_watched_requires_all_aired_episodes`
  - `test_watch_unknown_when_tautulli_fails` (Review Focus 1: Tautulli raises `IntegrationError` → `watch()` returns None for every item and the warning is logged once)
  - `test_watch_none_when_not_in_plex`
  - `test_requests_season_filter`
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5: Checkpoint.**

---

### Task 9: Item builders

**Files:** Modify `src/excludarr/items.py`. Create `tests/test_items.py` and `tests/fixtures/{radarr_movies,sonarr_series,sonarr_episodes,sonarr_episode_files}.json`.

**Interfaces:**
- `@dataclass(frozen=True) EpisodeRef(id: int, season: int, number: int, aired: bool, file_id: int | None, size_bytes: int, monitored: bool)`.
- `@dataclass MediaItem`, fields:
  - `key: str`, `kind: Literal["movie","series","season","episode"]`, `title: str`, `base_title: str`, `arr_id: int`, `season: int | None`, `episode: int | None`
  - `tmdb_id: int | None`, `imdb_id: str | None`, `tvdb_id: int | None`, `year: int | None`, `added: datetime | None`
  - `size_bytes: int`, `has_file: bool`, `monitored: bool`, `tags: frozenset[str]`, `genres: frozenset[str]`, `ratings: dict[str, float]`, `ended: bool | None`
  - `rank_from_latest: int | None`, `episodes: tuple[EpisodeRef, ...]`, `raw: dict`
- Keys: `radarr:movie:{id}`, `sonarr:series:{id}`, `sonarr:season:{id}:{s}`, `sonarr:episode:{id}:{s}:{e}`.
- Titles: `"Dune (2021)"`, `"Breaking Bad (2008)"`, `"Breaking Bad – S02"`, `"Breaking Bad – S02E03"`.
- `build_radarr_items(radarr: RadarrClient) -> list[MediaItem]`. Ratings are `{"tmdb": ratings.tmdb.value, "imdb": ratings.imdb.value}` (whichever are present). Tags are mapped to their labels.
- `build_sonarr_items(sonarr: SonarrClient, level: Literal["series","season","episode"]) -> list[MediaItem]`:
  - Season and episode items inherit the series' tmdb/imdb/tvdb ids, year, added, tags, genres, ratings (`{"sonarr": ratings.value}`) and `ended` (`status == "ended"`). This is spec §5.3.
  - `size_bytes` and `has_file` are aggregated from the episode files in the unit. `monitored` is the series, season or episode flag.
  - `rank_from_latest`: 0 is the most recent aired season (season level) or the most recent aired episode (episode level, ordered by season then number); season 0 is excluded; series items get `None`.
  - `aired` is true when `airDateUtc` exists and is ≤ now.
  - `episodes` holds the unit's EpisodeRefs (season 0 excluded at every level).

- [ ] **Step 1: Failing tests** against the fixtures: radarr item fields; `test_season_items_inherit_series_attributes`; `test_season_size_is_sum_of_episode_files`; `test_rank_from_latest_ignores_specials_and_unaired`; `test_episode_keys_and_titles`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5: Checkpoint.**

---

### Task 10: Conditions

**Files:** Create `src/excludarr/conditions.py`, `tests/test_conditions.py`. Modify `src/excludarr/config.py` so that `Rule.when: Condition` and `Rule.unless: list[Condition]` are parsed with `parse_condition`, and add the integration-availability validation.

**Interfaces:**
- Tree:
  - `@dataclass All(children: list[Condition])`, `@dataclass Any_(children)`, `@dataclass Not(child)`, `@dataclass Leaf(name: str, params: Any)`.
  - `Condition = All | Any_ | Not | Leaf`.
- `parse_condition(raw: Any) -> Condition`. YAML forms: `{all: [...]}`, `{any: [...]}`, `{not: {...}}`, or a single-key leaf dict such as `{streaming: my_providers}`. An unknown leaf name or a bad param raises `ValueError` naming the leaf.
- `required_integrations(cond) -> set[str]`, with values from `{"tautulli","plex","seerr"}`. Config validation raises a `ConfigError` naming the rule and the missing integration.
- `describe(cond) -> str`. Renders a compact sentence-like label, e.g. `"on my providers (flatrate)"`, `"added more than 180d ago"`, `"not watched for 30d"`, `"(A or (B and C))"`. It is used for preview reasons and per-condition counts.
- `evaluate(cond, item: MediaItem, ctx: Context) -> bool | None`. Combinators:
  - `All`: False if any child is False, else None if any child is None, else True.
  - `Any_`: True if any child is True, else None if any child is None, else False.
  - `Not`: inverts the child; None stays None.
- Leaf catalogue (spec §5.3). "→ None if facts unknown" applies to every leaf that needs facts.

| Leaf | Params | True when |
|---|---|---|
| `added_more_than` / `added_less_than` | duration | `now - added` >/< d (`added` None → None) |
| `size_more_than` / `size_less_than` | size | `size_bytes` >/< n |
| `tag` / `genre` | str or list | any listed value in `tags`/`genres` (case-insensitive) |
| `year` | `{min?, max?}` | inclusive range |
| `rating` | `{source?: tmdb\|imdb, min?, max?}` | radarr uses `source` (default tmdb); sonarr ignores `source` and uses `"sonarr"`; missing rating → None |
| `monitored` / `has_file` | bool | equality |
| `status` | `ended\|continuing` | sonarr only (validated) |
| `keep_latest` | `{seasons: N}` or `{episodes: N}` | `rank_from_latest >= N`; `seasons` only valid at season level, `episodes` only at episode level (validated) |
| `streaming` | `my_providers` or `{providers?: list\|my_providers, monetization?: list}` | `units = ctx.streaming(item)`; None → None; `units` empty → False; else every unit contains some `(pid, m)` with `pid` in `ctx.provider_ids(providers)` and `m` in the upper-cased monetization (default `["flatrate"]`) |
| `not_watched_for` / `watched_within` | duration | `last_watched` None or older than d / within d |
| `watched_by` | user | the user (lower-cased) is in `last_by_user` |
| `play_count` | `{min?, max?}` | inclusive range |
| `fully_watched` | bool | equality |
| `requested_by` | user | some request's `requested_by` contains the user (lower-cased); no requests → False |
| `requested_more_than` / `requested_less_than` | duration | judged on the **most recent** request's `created_at`; no requests → False |
| `requester_watched_more_than` | duration | no requests → None; for the most recent request, the requester's latest watch (any name in `requested_by` found in `last_by_user`) exists and is older than d; the requester never watched → False |

- [ ] **Step 1: Failing tests** (use a `FakeContext` with canned `streaming`/`watch`/`requests`/`provider_ids`):
  - The three-valued truth tables for All, Any_ and Not.
  - `test_user_rule_literal_or` and `test_user_rule_grouped`: the two variants from the brainstorm.
    - Literal: `any[streaming, added_more_than 180d, requester_watched_more_than 30d]`.
    - Grouped: `any[streaming, all[added_more_than 180d, not_watched_for 30d]]`.
    - The grouped variant must *not* match an item added 200d ago and watched 5d ago; the literal one must.
  - `test_streaming_season_requires_every_aired_episode`: episode 1 on Netflix and episode 2 only on Prime, with providers `[Netflix]` → False; with providers `[Netflix, Prime]` → True.
  - `test_streaming_monetization_filter`: only a `FREE` offer, default monetization → False; `monetization: [free]` → True.
  - `test_unknown_streaming_never_true_under_not`: `not streaming` with facts None → None.
  - `test_keep_latest`.
  - `test_parse_errors_name_the_leaf`.
  - `test_describe_grouping`.
  - `test_rule_using_tautulli_without_plex_rejected`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement with a registry `LEAVES: dict[str, LeafSpec(parse, integrations, targets, levels, evaluate)]`. **Step 4:** Run → PASS.
- [ ] **Step 5: Checkpoint.**

---

### Task 11: Actions and side effects

**Files:** Create `src/excludarr/actions.py`, `tests/test_actions.py`.

**Interfaces:**
- `@dataclass ActionResult(ok: bool, size_freed: int, detail: str, side_effect_errors: list[str])`.
- `execute(rule: Rule, item: MediaItem, ctx: Context) -> ActionResult`. The main action follows spec §5.4:

| action | radarr movie | sonarr series | sonarr season/episode |
|---|---|---|---|
| `delete` | `delete_movie(delete_files=rule.delete_files, add_exclusion=rule.import_exclusion)` | `delete_series(...)` | delete the unit's episode files + `set_episodes_monitored(False)`; for a season also set `season.monitored=False` via `update_series` |
| `delete_files` | `delete_movie_files(all)` + `monitored=False` via `update_movie` | delete all episode files + series `monitored=False` | same as `delete` |
| `unmonitor` / `monitor` | `update_movie` | `update_series` (series flag) | season flag via `update_series` / `set_episodes_monitored` |
| `monitor` + `search: true` | `search([id])` | `search(id)` | `search(id, season=…)` / `search(id, episode_ids=…)` |
| `tag` | `ensure_tag` + add the id to `tags` + update | same, series level | applies to the parent series |
| `import_exclusion` | `add_exclusion(tmdb_id, title, year)` | `add_exclusion(tvdb_id, base_title)` | applies to the parent series |

- `size_freed` = `item.size_bytes` for delete/delete_files when files were deleted, else 0.
- Side effects, only after a successful `delete`/`delete_files`, each in its own try/except, with failures appended to `side_effect_errors`:
  1. Queue cleanup: remove the queue records where `movieId == arr_id` (radarr), or where `seriesId == arr_id` and, at season/episode level, `episodeId` is in the unit's episode ids.
  2. Seerr: for a movie or series, `delete_media(media_id)` for every matching request. For a season or episode, re-fetch `episode_files(series_id)` and `delete_request(id)` for each request of that series whose requested seasons now all have zero episode files.
  3. Plex: `refresh(section_key)` when `ctx.plex_item(item)` is known.
- On a main-action exception: `ok=False`, `detail=str(exc)`, and no side effects are run.

- [ ] **Step 1: Failing tests** (fake clients recording calls):
  - `test_delete_files_keeps_movie_unmonitored`
  - `test_season_delete_removes_files_and_unmonitors`
  - `test_monitor_with_search_triggers_season_search`
  - `test_side_effect_failure_does_not_fail_action` (Review Focus 4: Seerr raises → `ok=True`, one error recorded)
  - `test_main_action_failure_skips_side_effects` (Review Focus 4)
  - `test_seerr_season_request_deleted_only_when_all_requested_seasons_empty`
  - `test_queue_items_removed_on_delete`
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5: Checkpoint.**

---

### Task 12: Engine (preview, grace queue, exceptions, collection)

**Files:** Create `src/excludarr/engine.py`, `tests/test_engine.py`.

**Interfaces:**
- `@dataclass Match(rule: Rule, item: MediaItem, reasons: list[str])`. `reasons` holds the `describe()` of each top-level `when` child that evaluated True.
- `@dataclass RuleReport(rule: Rule, matches: list[Match], condition_counts: dict[str, tuple[int, int]], executed: list[tuple[Match, ActionResult]], queued: list[tuple[Match, datetime]], pending: list[tuple[Match, datetime]], dropped: list[str])`. `condition_counts` maps a label to (true count, unknown count) for each top-level child of `when`.
- `evaluate_rule(rule, items, ctx, skip_keys: set[str]) -> RuleReport`. Pure: no writes. It skips items in `skip_keys`, in `repo.exceptions_for(rule.name)`, or whose series/movie was already removed in this run (see `run`). It keeps the items where `evaluate(when)` is True and every `unless` evaluates False.
- `run(ctx, *, dry_run: bool, rule_filter: str | None = None, select: Callable[[RuleReport], list[Match]] | None = None, confirm: Callable[[list[Match]], bool] = lambda m: True) -> list[RuleReport]`. Algorithm:
  1. Drop the queue rows whose rule is no longer in the config, and remove those items from the collection (Review Focus 3).
  2. Build the items once per (target, level) on demand. If any enabled rule uses `streaming`, call `ctx.prefetch_streaming` on the items.
  3. For each enabled rule in file order (filtered by `rule_filter`): `report = evaluate_rule(...)`. If `dry_run` or `rule.preview` is set, report only and continue.
  4. If `select` is given, `matches = select(report)` (interactive).
  5. With `grace_period == 0`: when `confirm(matches)` is true, `execute` each match, then `history_add`.
  6. With `grace_period > 0`:
     - A match not in the queue → `queue_add(due=now+grace)`; if `leaving_soon_collection` is set, add it to the collection.
     - A match in the queue and due → execute (subject to `confirm`). On success, `queue_remove` and remove it from the collection. On failure, keep it queued.
     - A match in the queue but not due → `pending`.
     - A queue row of this rule that no longer matches → `queue_remove`, remove from the collection, add to `dropped`.
  7. After a successful `delete`/`delete_files`, mark the item as removed. For a sonarr series that means its id; for a movie, its id; for a season or episode, its key. Later rules skip those items (Review Focus 5).
- Collection rule: for sonarr items the collection member is the parent show. Only remove the show when no other queue row of the same series remains.
- "Rescue once" needs no engine code: removing the queue row is enough, and the next run re-evaluates the item (spec §5.5).

- [ ] **Step 1: Failing tests** (FakeContext, real `Repo` on tmp sqlite, fake `execute` monkeypatched):
  - `test_preview_rule_changes_nothing`
  - `test_grace_enqueues_then_executes_when_due` (freeze `ctx.now`)
  - `test_queued_item_no_longer_matching_is_dropped`
  - `test_exception_skips_item`
  - `test_failed_execution_stays_queued`
  - `test_orphaned_queue_rows_dropped` (Review Focus 3)
  - `test_later_rule_skips_removed_items` (Review Focus 5)
  - `test_condition_counts_include_unknown`
  - `test_confirm_false_executes_nothing`
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5: Checkpoint.**

---

### Task 13: CLI commands and output

**Files:** Modify `src/excludarr/cli.py`. Create `src/excludarr/output.py`, `tests/test_cli_commands.py`.

**Interfaces:**
- Consumes: `load_config`, `database_url`, `Repo`, `Clients.from_config`, `Context`, `run`.
- Commands (all read `--config` from the global state):
  - `run [--rule NAME] [--interactive] [-y/--yes] [--sort title|size|date]`: executes with `dry_run=False`. Without `-y`, `confirm` asks `"Execute N actions (X GB)? [y/N]"`. `--interactive` passes a `select` that shows a numbered table and asks `"Numbers to skip (comma separated, empty = none)"`.
  - `preview [--rule NAME] [--sort …]`: `dry_run=True`.
  - `queue [--sort …]`: lists the rule, key, title, size and due date.
  - `rescue ITEM_KEY --rule NAME (--forever | --once)`: removes the queue row and the collection membership; `--forever` also adds an exception. If the user passes neither flag, prompt for the choice.
  - `exceptions list`, `exceptions remove ITEM_KEY --rule NAME`.
  - `history [--limit 100]`.
  - `config validate`: loads the config, resolves the provider names over the network, prints "OK" and the rules with their `describe(when)`.
- Output (in `output.py`):
  - Per rule: a header with the name and mode (`PREVIEW` / `AUTO, grace 14d`), then the condition-count table (label, matches, unknown), then the matches table (title, size, reasons), then the totals (count, GB).
  - Then the executed, queued, pending and dropped sections when they are not empty.
  - Sizes are shown in GB with 2 decimals.
- Exit codes: 0 on success; 1 on `ConfigError` (print the message without a traceback); 2 when any action failed.

- [ ] **Step 1: Failing tests** (CliRunner; monkeypatch `Clients.from_config` to return fakes):
  - `test_preview_prints_condition_counts_and_totals`
  - `test_run_without_yes_aborts_on_no`
  - `test_rescue_forever_adds_exception`
  - `test_config_error_exit_code_1_without_traceback`
  - `test_sort_by_size`
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5: Checkpoint.**

---

### Task 14: Docker, example config, docs

**Files:** Modify `Dockerfile`, `entrypoint.sh`, `.examples/excludarr-example.yml`, `.examples/docker-compose-example.yml`, `README.md`, `CHANGELOG.md`, `.github/workflows/release.yml`, `CLAUDE.md`. Delete `.examples/docker_example.env`.

- [ ] **Step 1:** `.examples/excludarr-example.yml`: the full v2 config with every integration and the rules from spec §5.1, each option commented. Add `tests/test_example_config.py`, which asserts `load_config(".examples/excludarr-example.yml")` validates once the env vars are set.
- [ ] **Step 2:** Dockerfile:
  - Base `python:3.12-alpine`; `pip install .`.
  - `ENV EXCLUDARR_CONFIG=/config/excludarr.yml`, `VOLUME /config`.
  - `entrypoint.sh`: with `CRON_MODE=true`, copy `/config/crontab` (fall back to `/etc/excludarr/crontab`) and run `crond -f`; otherwise `exec excludarr "$@"`.
  - Remove the env-to-YAML generation, because v2 rules do not fit in env vars (breaking change, spec §3).
- [ ] **Step 3:** `release.yml`: build with `pip install build && python -m build`, then publish the wheel and sdist. Keep the existing secrets and trigger.
- [ ] **Step 4:**
  - README: what v2 does, install (pip/Docker), config, the safety workflow (preview → grace → automatic), the CLI commands, and a migration note from v1 (old config and `radarr exclude`/`re-add` → rules). Remove the "no longer maintained" banner.
  - CHANGELOG: a `2.0.0` entry.
  - CLAUDE.md: update the commands and architecture to v2.
- [ ] **Step 5:** `docker build -t excludarr:dev . && docker run --rm excludarr:dev --version` prints 2.0.0. Run `.venv/bin/pytest -q && .venv/bin/ruff check src tests` → all green.
- [ ] **Step 6: Checkpoint.**
