# Excludarr v2 — Project 1: Library Rules (design)

Status: approved by user · Date: 2026-11-05

## 1. Intent

Excludarr started as "remove from Radarr/Sonarr whatever is already on my paid streaming services, so it does not eat disk space". It broke when JustWatch removed its REST API (fixed via GraphQL in `excludarr/excludarr` + PR haijeploeg/excludarr#96).

v2 turns Excludarr into a general **media-management tool on top of Radarr and Sonarr**: user-defined **rules** (conditions → action) decide what gets deleted, unmonitored, tagged or excluded. Streaming availability is one condition among many. Think Maintainerr, but:

- **useful without a media server** — Radarr/Sonarr + JustWatch alone must already deliver value; watch data (Tautulli), requests (Seerr) and Plex are optional add-ons;
- **rules a human can read** — Maintainerr's nested if/else/or construction is hard to understand; Excludarr rules must read like a sentence and show what each part matches.

The end goal is **fully automatic** library management. Safety comes from a preview-first workflow, not from keeping a human in the loop forever.

This is project 1 of 3. Later projects (separate designs): **2. list proxy** (Excludarr serves filtered Custom Lists to Radarr/Sonarr, so titles on your streaming services are never imported), **3. web UI** (+ daemon/scheduler, Helm chart). Project 1 must not block those: the rule/condition engine and the YAML rule format are reused by both.

## 2. Goals

1. New codebase (Python ≥ 3.12) with one core package; the CLI is a thin layer over it. Projects 2/3 add more thin layers (HTTP API, proxy, UI) over the same core.
2. A rule engine: conditions combined with `all` / `any` / `not` (arbitrary nesting), an `unless` block, one action per rule.
3. Profile defaults: locale + the user's streaming providers, used by every `streaming` condition unless overridden.
4. Safety workflow: preview mode by default per rule → optional per-rule grace period ("leaving soon") → execution. Fully automatic once the user switches preview off.
5. Rescue from the grace queue: "exclude forever" or "just this once".
6. Persistent state in SQLite (works in CLI mode too): grace queue, exceptions, history, external-data cache.
7. Integrations: Radarr v3+/v5, Sonarr v4 (required: at least one of the two), JustWatch (GraphQL), and optional Tautulli, Seerr, Plex.
8. Fold in the open issue wishes listed in §9.
9. Distribution: PyPI package + Docker image (cron mode, as today).

## 3. Non-goals (this project)

- List proxy (project 2), web UI, long-running daemon/scheduler, HTTP API, Helm chart (project 3).
- More than one Radarr or one Sonarr instance. (Config layout should not make adding this later painful, but do not build it.)
- Jellyfin/Emby support, notifications (Discord etc.).
- Backwards compatibility with v1 YAML configs or CLI commands. v2 is a breaking major.

## 4. Anti-goals (failure even if it "works")

- **Deleting anything the user has not previewed** under default settings. A new rule never acts until `preview` is explicitly turned off.
- **Acting on missing or uncertain data.** If a condition cannot be evaluated (JustWatch lookup failed or title not matched, Tautulli unreachable, Seerr has no request record), the condition is *unknown*, and an unknown result must never cause a destructive match. Evaluate with three-valued logic (true/false/unknown); a rule only acts on items where the whole expression is definitely true. Unknown counts are shown in preview so the user can see coverage.
- Title-based matching. Match on IDs (TMDB/IMDB/TVDB) only; titles are for display.
- Hanging runs / hammering JustWatch (old issues #60, "too many requests"): cache, timeouts, retries with backoff, bounded concurrency.

## 5. Decisions made with the user

### 5.1 Configuration (YAML)

Single YAML file (search path like v1, plus `--config` flag and `EXCLUDARR_CONFIG` env var). Secrets may be referenced as `${ENV_VAR}`. Sketch the user reacted to (shape, not final syntax):

```yaml
profile:
  locale: nl_NL
  providers: [Netflix, Amazon Prime Video]

integrations:
  radarr:   { url: http://radarr:7878, api_key: ... }
  sonarr:   { url: http://sonarr:8989, api_key: ... }
  tautulli: { url: http://tautulli:8181, api_key: ... }   # optional
  seerr:    { url: http://seerr:5055, api_key: ... }      # optional
  plex:     { url: http://plex:32400, token: ... }        # optional

rules:
  - name: Streaming or stale movies
    target: radarr
    preview: true
    grace_period: 14d
    leaving_soon_collection: true
    action: delete_files     # keep the entry so the rule below can re-monitor it
    when:
      any:
        - streaming: my_providers
        - all:
            - added_more_than: 180d
            - not_watched_for: 30d
    unless:
      - tag: keep

  - name: Unwatched seasons
    target: sonarr
    level: season            # default; each season is judged and removed on its own
    preview: true
    grace_period: 7d
    action: delete_files
    when:
      all:
        - added_more_than: 90d
        - not_watched_for: 60d

  - name: Monitor again when it leaves streaming   # replaces v1 "re-add"
    target: radarr
    action: monitor
    search: true
    when:
      all:
        - monitored: false
        - not: { streaming: my_providers }
```

The YAML rule format is the contract the web UI (project 3) will later read and write — keep it explicit and round-trippable (no YAML anchors magic required, stable key order when written back).

URL handling: normalize integration URLs (missing scheme → error with clear message; trailing slash stripped) — old issues #82/#83.

### 5.2 Rules

- Fields: `name` (unique), `target` (`radarr` | `sonarr`), `level` (Sonarr only: `series` | `season` | `episode`, **default `season`**: the user typically wants to remove an unwatched *season*, not the whole series), `when`, optional `unless`, `action` + action options, `preview` (default `true`), `grace_period` (default `0`), `leaving_soon_collection` (default `false`, requires Plex), `enabled` (default `true`).
- `unless` = a list of conditions; any true → item is skipped by this rule.
- Both of these must be expressible: `A or B or C` and `A or (B and C)`.
- Preview output per rule: the matching items (title, size, which condition(s) made it match), totals (count, GB), and **per-condition counts** (how many items each top-level condition matches on its own, and how many are unknown), so an over-broad condition is visible immediately.

### 5.3 Conditions (v1 catalogue)

Available only when the corresponding integration is configured; a rule using an unconfigured integration is a config validation error.

| Source | Conditions |
|---|---|
| Radarr/Sonarr | added more/less than (duration); size on disk; tag(s); genre(s); year; rating (TMDB/IMDB, min/max); monitored; has file; series status ended/continuing (Sonarr); keep latest N seasons/episodes (Sonarr trim — issue #29) |
| JustWatch | `streaming`: providers (default `my_providers` from profile, or explicit list) + monetization types (default `flatrate`; allow `free`, `ads`, `rent`, `buy` — org issue #30) |
| Tautulli | last watched (any user) more/less than; watched by user X; play count; fully watched |
| Seerr | requested by user X; requested more/less than ago; requester has (not) watched it (needs Seerr + Tautulli; map users via Plex username/email) |

Sonarr: conditions are evaluated at the rule's `level`. These roll-up semantics were decided by the assistant and should be checked by the user:

- **Streaming:** availability is per episode in JustWatch. A season counts as "on provider" when all its aired episodes are, and a series when all its seasons are (v1 behaviour, keep it).
- **Inheritance:** season and episode items inherit the series attributes (tags, genres, rating, year, status). Their `added` date is the latest `dateAdded` of the unit's episode files, falling back to the series `added` when the unit has no files.
- **Watch data rolls up conservatively:** at series or season level, `not_watched_for: 30d` is true only if *no* episode in that unit was watched in the last 30 days, so the most recent watch wins. Play count is the sum over the unit. "Fully watched" means every aired episode in the unit was watched.
- **Size and has-file** are aggregated over the unit.
- **Seerr requests** are tracked per season. A series counts as "requested by X" if any of its seasons was.
- **"Keep latest N":** a season/episode item matches when it is *not* among the latest N aired seasons/episodes of its series. It is only valid at season or episode level.

### 5.4 Actions

| Action | Radarr | Sonarr |
|---|---|---|
| `delete` | delete movie; options `delete_files`, `import_exclusion` | series: delete series (`delete_files`, `import_exclusion`); season/episode: delete episode files + unmonitor (Sonarr cannot delete a season entity) |
| `delete_files` | delete the movie's files + unmonitor; the movie entry stays in Radarr (v1 behaviour — lets a later `monitor` rule bring it back) | series: delete all episode files + unmonitor series; season/episode: same as `delete` |
| `unmonitor` | ✓ | series / season / episode |
| `monitor` | ✓ option `search: true` triggers a search (issue #58) | same |
| `tag` | add tag (create if missing) — "label instead of delete" (#34) | same, series level |
| `import_exclusion` | add to exclusion list without deleting | same |

Side effects of `delete` and `delete_files` (user decision):

- Remove matching items from the Radarr/Sonarr download queue (issues #80 / org #29).
- If Seerr is configured: clear the media/request record for the title (for Sonarr season/episode level, the affected seasons), so it can be requested again. The Seerr client therefore reads **and writes**.
- If Plex is configured: trigger a refresh/scan of the affected library section so Plex drops the removed files.
- Each side effect is a separate step with its own failure handling. A failed side effect is logged in history and reported, but it does not roll back the main action.

### 5.5 Safety workflow

1. **Preview mode** (`preview: true`, the default): a run only reports what the rule would do. Nothing is queued or executed.
2. User switches `preview: false` → from then on runs act automatically.
3. **Grace period** (per rule, default 0): newly matching items enter the grace queue with a due date instead of being executed. While queued, if `leaving_soon_collection: true`, the item is added to a Plex collection "Leaving Soon" (name configurable) and removed from it when executed or rescued.
4. At each run, due items are **re-evaluated**; still matching → execute; no longer matching → drop from queue (and collection).
5. **Rescue**: removing an item from the queue asks: *exclude forever* (persistent exception for this rule) or *just this once* (dropped; the rule re-evaluates it on later runs — e.g. a "watched in the last 30 days" condition then naturally keeps it).
6. **Interactive approval** (issue #63): `--interactive` lets the user tick off individual items from a preview before they are queued/executed.
7. Every executed action is written to history (when, rule, item, action, size freed).

### 5.6 CLI (thin layer over the core)

Command set (names are the builder's call, the capabilities are not):

- `run [--rule NAME] [--interactive] [-y]` — evaluate all enabled rules; preview-mode rules report, others queue/execute.
- `preview [--rule NAME]` — force report-only for all rules (dry run).
- `queue` — list grace queue; `rescue ITEM --forever|--once`.
- `exceptions` — list/remove persistent exceptions.
- `history`.
- `providers list [--locale]` — list JustWatch providers for a locale (kept from v1).
- `config validate`.

Output: rich tables, sortable (issue #59: sort by title/size/date). Non-interactive mode for cron (`-y`).

### 5.7 Storage

SQLite file (path configurable; default next to config / `/config` in Docker). Holds: grace queue, exceptions, history, cache of JustWatch/TMDB lookups with TTL. Use a migration tool (schema will grow in projects 2/3). Postgres support is a project-3 concern; keep the data layer DB-agnostic (e.g. SQLAlchemy) so it is cheap later.

### 5.8 Packaging & runtime

- One package `excludarr`, entry point `excludarr`. Docker image runs it in cron mode (as v1 `entrypoint.sh`) or as a one-shot command.
- Tests: pytest; integration clients tested against recorded/fixture HTTP responses — no live services needed in CI.

## 6. Reuse from the existing code

Base code: `excludarr/excludarr` `main` + commit `62edb09`. Reuse ideas/code, not structure:

- JustWatch GraphQL client (`modules/justwatch/{justwatch,queries,models}.py`) incl. User-Agent and `packages` provider query. Provider matching key = JustWatch `packageId`; offer filter uses `shortName`.
- Sonarr season/episode streaming logic (`core/sonarr_actions.py`).
- pyarr has lagged behind the *arr APIs (issues #87, `patch_pyarr.py`). Builder decides whether to keep pyarr or talk to the v3 APIs directly with httpx.

## 7. Left to the builder

- Package layout, library choices (Typer is already used and fine), exact YAML key names and duration syntax beyond the sketch.
- Rule ordering/conflicts when two rules match the same item (suggestion: rules run in file order; an item already deleted in this run is skipped by later rules; document the behaviour).
- Cache TTLs, concurrency limits, retry policy.
- Schema/migration tool choice.

## 8. Success

- The user's real setup (Plex + Tautulli + Seerr, one Radarr, one Sonarr, NL providers) runs fully automatic on a cron schedule with their own rules, after a preview phase, without surprises.
- Someone with only Radarr + Sonarr + a JustWatch locale gets the v1 behaviour ("delete what's on my providers", "monitor again when it leaves") from two short rules.

## 9. Open issues folded in

#84 tag exclusion (`unless: tag`), #34 tag instead of delete, #78/#91/#88 ID matching & Sonarr v4, #60 hangs (cache/timeouts), #58 search on monitor, #80/org #29 queue cleanup on delete, #29 trim series, #63 interactive approval, org #30 monetization types, #59 sorted output, #82/#83 URL normalization.
