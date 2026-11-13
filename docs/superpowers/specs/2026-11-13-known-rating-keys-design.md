# Known rating keys

Status: approved

## Problem

Watch facts need a Plex rating key. `Facts.watch()` gets that key from a live Plex library scan (`plex_item()`), and then filters the Tautulli history by `rating_key` (movies) or `grandparent_rating_key` (series, seasons and episodes). If Plex no longer has the item, `watch()` returns unknown.

A `delete_files` action keeps the item in Radarr or Sonarr as unmonitored, but Plex removes it when the files go and the trash is emptied. A later rule such as `action: monitor` with `unless:` a watch condition can never act. The `unless` value stays unknown, and an unknown value never authorizes an action. The same applies to every watch-based leaf (`watched`, watch age, play count, requester watch) for movies and series.

A test on the user's server (2026-11-13, new Plex agents, `autoEmptyTrash` on) confirmed that a removed and re-added item gets a new rating key:

| Item | Old key | New key | Plex guid | Tautulli rows (old / new key) |
|---|---|---|---|---|
| The Brave Little Toaster (movie) | 3479 | 6591 | unchanged | 1 / 0 |
| Drain the Oceans (show) | 279 | 6592 | unchanged | 1 / 0 |

Tautulli does not follow the change. Its "Fix Match" remap (`update_metadata_details`) is a manual admin action per item. So an item that excludarr monitors again and that is downloaded again also loses its watch history.

## Decision

Excludarr remembers every rating key that Plex gave to an external id. Watch facts use all known rating keys of an item. Tautulli stays the only source of watch history. Excludarr stores identity only.

### Storage

- Add a new table with an alembic migration (`0006`). One row per (Plex type, external id, rating key), with the time the row was first seen.
- The Plex type is `movie` or `show`, as in `items_by_guid()`.
- Terms: the **Plex guid** is the item's own `guid` attribute (`plex://movie/…`, `plex://show/…`). An **external id** is one entry of the item's `Guid` list (`tmdb://…`, `imdb://…`, `tvdb://…`), which Plex returns with `includeGuids=1`. Excludarr stores external ids, not Plex guids.
- Rows never expire. Do not use the `cache` table: it has TTL semantics.

### Capture

- Each time `items_by_guid()` runs, upsert every `(type, external id) → rating key` pair that it returned. A pair that is already stored stays unchanged.
- A Plex "Fix Match" (rematch in Plex) keeps the rating key but changes its Plex guid and external ids. A test on 2026-11-13 confirmed this: key 6591 went from `tmdb://19933` to `tmdb://20378` and back. So when a scan returns a rating key, delete the stored rows for that key whose external id the scan did not return for it. Otherwise a stale row can credit the plays of another title to this external id.
- Never delete a row because the scan did not return its rating key. A re-add removes the old key from Plex, and the old key must stay to match the earlier plays. Tautulli's own "Fix Match" (remap of history to a new key) needs no handling: the old and new keys are both known.
- Run the scan once per run when Plex and Tautulli are configured and any enabled rule uses a watch leaf, also when no item evaluates that leaf. Reason: `unless` is evaluated only when `when` is True (`engine.py`), so the lazy scan can skip every run in which the item is still in Plex. Then its key is never stored. One scan returns the whole library, so the cost is one scan per run.
- A failed Plex scan writes and deletes nothing.

### Watch lookup

- Collect the rating keys of the item: the live `plex_item()` match, if any, plus every stored rating key for the item's tmdb, imdb and tvdb external ids of the same type.
- Filter the Tautulli history on all collected keys. Movies use `rating_key`. Series, seasons and episodes use `grandparent_rating_key`, with the existing season, episode and specials filters.
- Series, seasons and episodes all use the stored rating keys of the show. Only shows and movies are stored. Season and episode numbers come from the Tautulli rows (`parent_media_index`, `media_index`), not from Plex. Renumbering after a rematch or an order change is out of scope.
- If Plex is down or no longer has the item, use the stored keys. `watch()` returns unknown only when no rating key is known, or when the Tautulli history is unavailable.
- Limit: while Plex is down, plays under a new rating key that no scan has stored yet are not counted.
- `movie_viewer_labels()` shows "Not in Plex" only when no rating key is known.
- Plex writes (Leaving Soon collection, library refresh) keep the live lookup only. A stored key can point at an item that Plex removed.

### Behaviour change

Play count, last-watched date, fully-watched state and viewers can increase for an item that Plex re-added. Its plays under older rating keys now count. This is the intended result. Note it in the changelog.

Watch leaves in `when` can now be known for an item without files. A `delete_files` rule then skips movies and series that have no files and are already unmonitored: the action changes nothing for them, and each run would add a history row. A monitored item without files still matches, because the action unmonitors it; existing configs can rely on that. A `delete` rule can still remove an entry without files.

### CLI

Add a command group `rating-keys` with one command, `prune`:

- `excludarr rating-keys prune` deletes all rows of a rating key when none of its external ids matches a current Radarr movie or Sonarr series. A key keeps all its rows while one id matches, because Plex lists ids that Radarr and Sonarr do not have, such as the tvdb id of a movie. Items that are unmonitored but still in Radarr or Sonarr keep their rows.
- Report the number of removed rating keys, not rows.
- Support `-o table|json|yaml`, as the other commands do.
- If Radarr or Sonarr fails to answer, delete nothing and exit with the normal integration error status. A partial item list must not remove rows.
- Do not add a command to delete all rows (YAGNI).

Prune is a manual choice. If a movie is deleted from Radarr, pruned, and added to Radarr again later, its old plays are not found.

## Scope

- In scope: the new Plex agents (`tv.plex.agents.movie`, `tv.plex.agents.series`). Plex marks the legacy agents as deprecated. Legacy external ids that the scan returns (for example `com.plexapp.agents.imdb://…`) are stored as they are, but no special handling or tests are added for them.
- No backfill. Items that Plex removed before this release have no known rating key and stay unknown. Tautulli cannot map an old rating key to an external id: history rows carry only the Plex guid, and the `get_metadata` API has no database fallback.
- One Plex server and one Tautulli. No change to the configuration.

## Rejected approaches

- **Match on Tautulli data only.** History rows have no tmdb, imdb or tvdb id. Excludarr can not get from a Radarr/Sonarr item to its plays without a rating key.
- **Tautulli `guid` filter with the Plex guid.** It works for movies, because the Plex guid survives a re-add. Episode rows carry the Plex guid of the episode, not of the show, so it fails for series. It also needs a plex.tv lookup from the external id to the Plex guid.
- **Title and year match on history rows.** This is unreliable with remakes, renames and localized titles.
- **Store the Plex guid instead of rating keys.** For movies this is enough: history rows carry the Plex guid, and it survives a re-add. Series still need rating keys, because the only link from an episode row to its show is `grandparent_rating_key`. Rating keys for both kinds keep one mechanism.
- **Only the latest rating key per external id.** A re-add overwrites the old key, and the old plays are lost (see the test above).
- **Store the key only on a delete action.** This misses items that were removed outside excludarr.
- **Maintainerr's approach.** It queries Tautulli only with the live rating key and evaluates only items that Plex has. It does not solve this case.

## Acceptance

Tests use respx and fakes, with no network.

- A Plex scan stores its `(type, external id, rating key)` pairs, and a second scan adds no duplicate rows.
- A scan that returns a stored rating key under a different external id removes the stale row.
- A run in which a watch rule exists but no item evaluates a watch leaf still scans Plex and stores keys. A later run then gets known watch facts after Plex removed the item.
- An item that Plex no longer has, with a stored key and Tautulli rows, gets known watch facts. A `monitor` rule with `unless: watched` then acts or skips as the history says.
- An item with an old stored key and a different live key combines the rows of both keys, for a movie and for a series.
- After a Tautulli "Fix Match" moves the rows from the old key to the new key, watch facts do not change. Each history row counts once, also when several known keys apply.
- If the Plex scan fails, watch facts come from the stored keys.
- If the Tautulli history fails, watch facts stay unknown.
- An item with no stored key and no Plex match stays unknown, as today.
- `rating-keys prune` deletes rows for external ids that are no longer in Radarr or Sonarr, keeps rows for unmonitored items, and deletes nothing if an integration fails.
- The migration upgrades an existing 2.4.0 database.

Manual check: on the user's server, *The Brave Little Toaster* (keys 3479 and 6591) and *Drain the Oceans* (keys 279 and 6592) are real re-add cases. Do not remap them in Tautulli before this check. The old keys are not captured automatically, because Plex removed them before the release. Insert them by hand in a test database, then confirm that both items report their earlier play.

The builder chooses the table and column names, the repo method names and the exact report fields.
