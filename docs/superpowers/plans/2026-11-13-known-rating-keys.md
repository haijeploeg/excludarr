# Known Rating Keys Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Watch facts stay known after Plex removes or re-adds an item. Excludarr stores every rating key that Plex gave to an external id, and matches Tautulli history on all of them.

**Architecture:** A new `known_rating_key` table holds `(kind, external_id, rating_key)` rows. `Context` records the pairs from each successful Plex scan and reads them back in `watch()`. `engine.run` starts one Plex scan per run when a rule uses a watch leaf. A new `rating-keys prune` command removes rows for items that Radarr and Sonarr no longer have.

**Tech Stack:** Python ≥ 3.12, SQLAlchemy, Alembic, Typer, pytest, respx, Ruff.

**Spec:** [Known rating keys](../specs/2026-11-13-known-rating-keys-design.md).

## Global Constraints

- Tautulli stays the only source of watch history. The table stores identity only.
- Plex writes (`engine._collection`, `engine._uncollect`, `actions._refresh_plex`) keep the live `ctx.plex_item()` lookup. Do not give them stored keys.
- Count each Tautulli row once: filter the history in one pass with `key in known_keys`.
- A failed Plex scan writes and deletes nothing. A failed Radarr or Sonarr call during `prune` deletes nothing.
- Never delete a row because a scan did not return its rating key.
- Use the existing no-network fakes. Run commands with `.venv/bin/`. Do not commit without the user's instruction. Commit messages are Conventional Commits, with no AI attribution.
- Do not edit `CHANGELOG.md`: python-semantic-release writes it. Put the behaviour change in the `feat` commit body.

## Review Focus

1. A movie is re-added as a new key. The plays under the old key and the new key both count, and no play counts twice. Task 3.
2. A Plex rematch moves key `6591` from `tmdb://19933` to `tmdb://20378`. The `19933` row is deleted, and the old rows of other keys stay. Task 1.
3. Plex is down. Watch facts come from stored keys. Leaving Soon and refresh do not use stored keys. Task 3.
4. A rule's only watch leaf is in `unless`, and `when` is false for every item. The run still scans Plex and stores keys. Task 4.
5. Sonarr fails during `prune`. No row is deleted. Task 5.

## File responsibilities

- `storage/models.py`, `storage/repo.py` and migration `0006_known_rating_keys.py` own the table and its three operations.
- `facts.py` records the keys after a scan and builds the key set for `watch()`.
- `engine.py` decides when to scan Plex eagerly.
- `cli.py` and `output.py` own `rating-keys prune`.

### Task 1: Table, migration and repo methods

**Files:** Modify `src/excludarr/storage/models.py` and `src/excludarr/storage/repo.py`. Create `src/excludarr/storage/migrations/versions/0006_known_rating_keys.py`. Test `tests/test_repo.py`.

**Interfaces:**

```python
class KnownRatingKey(Base):
    __tablename__ = "known_rating_key"
    kind: Mapped[str] = mapped_column(String, primary_key=True)         # "movie" | "show"
    external_id: Mapped[str] = mapped_column(String, primary_key=True)  # "tmdb://19933"
    rating_key: Mapped[str] = mapped_column(String, primary_key=True)
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)

# Repo
def rating_keys_record(self, pairs: dict[tuple[str, str], str]) -> None: ...
def rating_keys_for(self, kind: str, external_ids: Iterable[str]) -> set[str]: ...
def rating_keys_prune(self, kinds: set[str], keep: set[tuple[str, str]]) -> int: ...  # only rows of `kinds`
```

`pairs` has the same shape as `items_by_guid()`: `(kind, external_id) → rating_key`.

- [ ] Write the tests first:
  - `test_rating_keys_record_is_idempotent`: record the same pairs twice. One row per pair, and `first_seen_at` is unchanged.
  - `test_rating_keys_keep_old_keys_after_readd`: record `{("movie","tmdb://1"): "100"}`, then `{("movie","tmdb://1"): "200"}`. `rating_keys_for("movie", ["tmdb://1"])` is `{"100", "200"}`.
  - `test_rating_keys_rematch_removes_stale_external_id`: record `{("movie","tmdb://1"): "100", ("movie","imdb://tt1"): "100"}`, then `{("movie","tmdb://2"): "100"}`. Only `("movie","tmdb://2","100")` stays for key `100`.
  - `test_rating_keys_prune_keeps_listed_ids`: `rating_keys_prune({"movie"}, keep={("movie","tmdb://1")})` deletes the other movie rows, keeps all show rows, and returns the number of deleted rows.
  - Extend `test_migrations_idempotent` or add `test_known_rating_key_migration_upgrades_existing_db`: a database at revision `0005` with rows upgrades to head, and the old rows stay.
- [ ] Run `.venv/bin/pytest -q tests/test_repo.py`. Expect failures.
- [ ] Add the model, then migration `0006` (`down_revision = "0005"`) with `op.create_table` in the style of `0004_list_snapshots.py`, and `drop_table` in `downgrade`.
- [ ] Implement `rating_keys_record` in one `with Session(self._engine) as s, s.begin():` block, as the other repo methods do:
  1. Build the wanted triples `{(kind, external_id, rating_key)}` from `pairs`, and the set of seen rating keys.
  2. Read the stored triples for the seen rating keys with one `select(...).where(KnownRatingKey.rating_key.in_(seen_keys))`.
  3. Delete the stored triples that are not wanted with `s.execute(delete(KnownRatingKey).where(...))`. These are rematched rows.
  4. `s.add` a `KnownRatingKey(..., first_seen_at=_now())` for each wanted triple that is not stored. Do not use `s.merge`: it would overwrite `first_seen_at`.
  5. Leave rows with rating keys that are not seen untouched.
- [ ] Implement `rating_keys_prune` with `s.execute(delete(KnownRatingKey).where(...))`, and return `result.rowcount`. Implement `rating_keys_for` with one `select`.
- [ ] Run `.venv/bin/pytest -q tests/test_repo.py`. Expect all tests to pass.

### Task 2: Record keys after each Plex scan

**Files:** Modify `src/excludarr/facts.py`. Test `tests/test_facts_watch_requests.py`.

**Interfaces:** Add `Context.plex_library() -> dict[tuple[str, str], PlexItem] | None`. It wraps `self._once("plex", self._scan_plex)`. `_scan_plex` calls `self.clients.plex.items_by_guid()`, then `self.repo.rating_keys_record({k: v.rating_key for k, v in result.items()})`, and returns the result. `plex_item()` uses `plex_library()`.

- [ ] Write the tests first:
  - `test_plex_scan_records_rating_keys`: after `ctx.watch(movie)`, `repo.rating_keys_for("movie", ["tmdb://11"]) == {"m1"}`.
  - `test_failed_plex_scan_records_nothing`: `BrokenPlex` leaves the table empty.
  - `test_plex_fetched_once` keeps passing: the scan runs once per run, also with recording.
- [ ] Implement. If `rating_keys_record` raises, log a warning and still return the scan. A storage failure must not hide live Plex data. The live data is still correct.
- [ ] Run `.venv/bin/pytest -q tests/test_facts_watch_requests.py`.

### Task 3: Watch facts from all known keys

**Files:** Modify `src/excludarr/facts.py`. Test `tests/test_facts_watch_requests.py`.

**Interfaces:** Add `Context.rating_keys(item) -> set[str]`. Use the same `kind` mapping as `plex_item()` (`"movie"` for movies, `"show"` for series, seasons and episodes) and the external ids `tmdb://{item.tmdb_id}`, `imdb://{item.imdb_id}`, `tvdb://{item.tvdb_id}` that are set. Return the live `plex_item(item).rating_key` (if any) plus `repo.rating_keys_for(kind, ids)`. Memoize per `(kind, ids)` within the run.

- [ ] Write the tests first. Use a `Repo` with rows recorded through `repo.rating_keys_record` before the context runs:
  - `test_watch_uses_stored_key_when_item_left_plex`: Plex has no item; stored `("movie","tmdb://11") → "old"`; a watched row under `"old"`. `watch()` returns `play_count == 1`, `fully_watched is True`.
  - `test_watch_combines_old_and_live_keys_movie`: live key `m1` plus stored `"old"`; one row under each. `play_count == 2`.
  - `test_watch_combines_old_and_live_keys_series`: as above with `grandparent_rating_key` for a season item; the season filter still applies.
  - `test_watch_counts_each_row_once_after_tautulli_remap`: stored `"old"` and live `m1`; the single row is under `m1` only. `play_count == 1`.
  - `test_watch_uses_stored_keys_when_plex_fails`: `BrokenPlex`, stored key, Tautulli rows. Watch facts are known.
  - `test_watch_unknown_without_any_key`: no Plex match and no stored key. `watch()` is `None`, as today (`test_watch_none_when_not_in_plex` keeps passing).
  - `test_watch_unknown_when_tautulli_fails` keeps passing with stored keys present.
  - `test_viewer_labels_not_in_plex_only_without_keys`: with a stored key and no Plex match, `movie_viewer_labels()` does not return `["Not in Plex"]`.
- [ ] Implement in `watch()`:
  - Replace the `plex_item is None` early return with `keys = self.rating_keys(item)`. If `keys` is empty, return `None` with the existing debug reasons.
  - Filter movies with `r.rating_key in keys` and the others with `r.grandparent_rating_key in keys`. Keep the season, episode and specials filters.
  - In `movie_viewer_labels()`, return `["Not in Plex"]` only when `self.rating_keys(item)` is empty and Plex did not fail.
- [ ] Keep `plex_item()` unchanged for the callers in `engine.py:153` and `actions.py:152`.
- [ ] Run `.venv/bin/pytest -q tests/test_facts_watch_requests.py tests/test_conditions.py`.

### Task 4: One Plex scan per run when a rule uses watch facts

**Files:** Modify `src/excludarr/engine.py`. Test `tests/test_engine.py`.

**Interfaces:** None new. Use `LEAVES[leaf.name].integrations` (`TAUTULLI = {"tautulli", "plex"}` in `conditions.py`).

- [ ] Write the test first: `test_run_scans_plex_when_watch_rule_never_evaluates_watch`. The rule has `when` false for every item and a watch leaf only in `unless`. After `engine.run(...)`, the fake Plex `calls == 1` and the table holds its pairs. Add a contrast case: with no watch leaf in any rule, `calls == 0`.
- [ ] In `engine.run`, before the rule loop: if `ctx.clients.plex and ctx.clients.tautulli` and any selected, enabled rule has a leaf with `"tautulli"` in `LEAVES[leaf.name].integrations` (check `[rule.when, *rule.unless]`, as `uses_streaming` does), call `ctx.plex_library()`. Its failure is already handled by `_once`.
- [ ] Run `.venv/bin/pytest -q tests/test_engine.py`.

### Task 5: `excludarr rating-keys prune`

**Files:** Modify `src/excludarr/cli.py` and `src/excludarr/output.py`. Add a `rating_keys_prune` projection in `src/excludarr/reporting.py` if the other commands build their documents there. Test `tests/test_cli_commands.py`.

**Behaviour:**
- Build `keep` from `ctx.clients.radarr.movies()` as `("movie", "tmdb://{tmdbId}")` and `("movie", "imdb://{imdbId}")`. Build it from `ctx.clients.sonarr.series()` as `("show", "tvdb://{tvdbId}")`, `("show", "tmdb://{tmdbId}")` and `("show", "imdb://{imdbId}")`. Skip empty or zero ids.
- If Radarr or Sonarr is not configured, only that kind is pruned. Do not delete rows of an unconfigured kind.
- Fetch both lists before any delete. On `IntegrationError`, raise it so that `_command` reports it with the normal exit status, and delete nothing.
- Call `repo.rating_keys_prune(kinds, keep)`, with `kinds` the configured kinds (`"movie"` for Radarr, `"show"` for Sonarr). Report `{"removed": n}`. Table output prints one heading line, for example `Removed 3 known rating keys`.

- [ ] Write the tests first:
  - `test_rating_keys_prune_removes_ids_not_in_arr`: one stored movie id is not in Radarr and one is. `removed == 1`, and the kept row stays.
  - `test_rating_keys_prune_keeps_unmonitored_items`: a movie with `monitored: False` in Radarr keeps its row.
  - `test_rating_keys_prune_deletes_nothing_on_integration_error`: Sonarr raises. Non-zero exit, and all rows stay.
  - `test_rating_keys_prune_json`: `-o json` prints one parseable document with `removed`.
- [ ] Add `rating_keys_app = typer.Typer(help="Known Plex rating keys.", no_args_is_help=True)` and `@rating_keys_app.command("prune")`, following `cache status`.
- [ ] Run `.venv/bin/pytest -q tests/test_cli_commands.py -k rating_keys`.

### Task 6: Docs and full check

**Files:** Modify `README.md` and `AGENTS.md`.

- [ ] `README.md`: describe in two or three sentences that watch history stays known after Plex removes or re-adds an item. Say that this starts from the first run after the upgrade. Document `excludarr rating-keys prune`.
- [ ] `AGENTS.md`: under `storage/`, mention the known rating keys table. Under `facts.py`, mention that `watch()` uses live and stored rating keys.
- [ ] Run `.venv/bin/ruff format src tests && .venv/bin/ruff check src tests && .venv/bin/pytest -q`. Expect all tests to pass.
- [ ] Run `.venv/bin/excludarr --config .examples/excludarr-example.yml config validate`.

### Task 7: Manual check on the user's server

Ask the user before each step. These items are real re-add cases from the spec test:
- *The Brave Little Toaster*: old key `3479`, live key `6591`.
- *Drain the Oceans*: old key `279`, live key `6592`.

- [ ] Run the new build against a copy of the production database, never the live one.
- [ ] Insert the old keys by hand: `("movie","tmdb://19933","3479")` and `("show","tvdb://348352","279")`.
- [ ] Run `excludarr preview --show-all` for a rule that targets these items. Confirm that both report their earlier play, and that the movie's viewers are no longer unknown.
- [ ] Report the result. Do not remap these items in Tautulli before this check.

## Commit

One commit after all tasks pass, when the user asks:

```
feat: keep watch history after Plex re-adds an item

Store every Plex rating key seen per external id and match Tautulli
history on all of them. Watch facts stay known after Plex removes an
item, and plays under an earlier rating key now count. Add
`excludarr rating-keys prune`.
```
