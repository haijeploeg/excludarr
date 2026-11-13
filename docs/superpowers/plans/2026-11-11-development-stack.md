# Seeded Development Stack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking. Preserve the previously chosen inline execution method; use one independent final reviewer.

**Goal:** Run the full real integration suite locally with disposable generated media and repeatable seeded scenarios.

**Architecture:** One dedicated Compose project runs Radarr, Sonarr, Plex, Tautulli, Seerr and locally built Excludarr. A development tooling container generates fixtures, calls service APIs, writes separate preview/action configurations and verifies real outcomes. Plex account authentication is a documented local prerequisite for the full chain, not a mocked step.

**Tech Stack:** Docker Compose, existing Python/httpx/PyYAML dependencies, stdlib sqlite3 for generating an import fixture, FFmpeg in a development-only image, real service APIs.

**Spec:** `docs/superpowers/specs/2026-11-11-development-stack-design.md` (approved).

## Global Constraints

- No commits without a request. Preserve existing daemon changes on `feat/daemon`.
- No production config mounts, Docker socket, host networking or production credentials.
- Distinct host ports bound only to 127.0.0.1; project-scoped named volumes and bridge network.
- No new production list source or mocked integration client is introduced.
- Keep unit tests offline; destructive integration checks are an explicit separate command.
- Default config has preview rules and a separate state database.
- Real external Popular/Trending/saved/watchlist providers are separately documented optional smoke checks.
- No indexers or download clients are configured and no copyrighted media is downloaded.
- Repository artifacts are English. Do not print tokens or commit account data.

## Review Focus

1. Wrong stack identity or endpoint: refuse mutations before any API write or deletion (tasks 1, 4).
2. Retry after partial initialization: rerunning seed must repair missing data without duplicates (tasks 2, 3).
3. Missing login, delayed matching or unavailable metadata: bounded waits and precise incomplete status (tasks 2, 3).
4. History import changes rating keys or user identity: validate the pinned schema and read back actual watch facts (task 3).
5. Preview, daemon or reset affects controls or unrelated state: compare API/file controls and scope reset to the project (task 4).

## File Map and Command Contract

- Replace `docker-compose.yml`: development project `excludarr-dev`; services `radarr`, `sonarr`, `plex`, `tautulli`, `seerr`, `fixtures`, `tools`, `excludarr`.
- Create `dev/Dockerfile`: install the local project and development tooling dependencies/FFmpeg; do not enlarge the production image.
- Create `dev/stack.py`: fixed service addresses, bounded API operations, identity checks, seed orchestration and argparse entrypoint.
- Create `dev/fixtures.json`: versioned media IDs, filenames and per-item scenario roles; no credentials or database row IDs.
- Create `dev/history.py`: generate the pinned Tautulli import database from resolved IDs.
- Create `dev/checks.py`: explicit real integration scenarios, invoked by stack.py.
- Create `dev/__init__.py`, `tests/test_dev_stack.py`, `tests/test_dev_history.py`: imports and meaningful offline checks.
- Modify `.gitignore`, `.github/DEVELOPER.md`, `README.md`: local credential handling, commands and scenario matrix.

Use `docker compose -p excludarr-dev ...` consistently. Host ports: Radarr 17878,
Sonarr 18989, Plex 32410, Tautulli 18181, Seerr 15055, Excludarr 18990. Tools run
`python -m dev.stack`; subcommands `seed`, `status`, `check`; `seed --arr-only`
permits independent Arr validation before login. `check --arr-only` runs only the
documented Arr subset and reports the full-chain checks as skipped.

Generated `/config/preview.yml` and `/config/actions.yml` use separate SQLite files;
`/config/daemon.yml` uses the action state database so contention tests exercise the
same locks. Tools and Excludarr share only development config/state volumes. The tools
service may mount development service configuration volumes needed for first-run
setup/keys; it never mounts production files. Account env file: `dev/.env.local`,
explicitly ignored and passed via Compose `--env-file` when needed.

### Task 1: Isolated service lifecycle and readiness

**Files:** docker-compose.yml, dev/Dockerfile, dev/stack.py, dev/__init__.py, .gitignore, tests/test_dev_stack.py.

**Interfaces:** `request(service: str, method: str, path: str, **kwargs) -> dict | list`;
`wait_ready(service: str, timeout: float = 180) -> None`;
`verify_stack(*, full: bool) -> dict` returns the validated instance identity record;
`main() -> None` maps setup failures to a concise nonzero exit.

- [x] Write offline tests asserting fixed internal origins, reject redirects to other hosts, refuse mismatched identity/marker, bounded readiness failure, and redaction of errors containing credentials. Use respx and temporary paths, not Docker in pytest.
- [x] Run `.venv/bin/pytest tests/test_dev_stack.py -q`; confirm failures before implementation.
- [x] Verify primary image documentation/registry manifests; choose explicit compatible ARM64 tags/digests, record versions and startup API/auth configuration. Implement the Compose services and minimal tooling above. Make `tools` and `excludarr` opt-in so no daemon starts before seed. The deterministic `fixtures` HTTP service serves only its fixed fixture directory on the internal network.
- [x] Bootstrap generated Arr keys/config on first initialization only, using the pinned images' supported initialization/configuration; wait until APIs respond. Persist generated credentials locally. Readiness checks identify missing Plex authentication without printing token values.
- [x] Run offline tests, `docker compose -p excludarr-dev config --quiet`, build images and start the five services plus fixtures. Verify localhost endpoints and isolated mounts. No reset of the user's existing containers or volumes.

### Task 2: Generated media and repeatable Arr seed

**Files:** dev/fixtures.json, dev/stack.py, tests/test_dev_stack.py.

**Interfaces:** `seed_arr(manifest: dict) -> dict` resolves fixture role to actual API IDs,
paths and external IDs; `seed(*, arr_only: bool = False) -> dict` orchestrates readiness,
seed and state persistence. Preserve progress after each verified service step.

- [x] Add tests `test_seed_arr_reuses_existing_ids`, `test_seed_arr_repairs_deleted_fixture`, `test_seed_failure_retains_completed_steps` and `test_manifest_rejects_unsafe_paths`. Assert no duplicates, no assumed numeric root/profile IDs, no search/download commands, and no mutation before identity validation.
- [x] Run these tests and confirm the new assertions fail.
- [x] Implement a small role-based manifest of real metadata IDs. Generate a valid short video/audio clip once using FFmpeg, copy it to fixture movie/episode paths, and seed metadata through actual Arr APIs. Discover profiles/root folders, wait for imported movie/episode files and verify external IDs/path ownership. Include missing-file and protected controls and enough independent action subjects to avoid destructive test interference.
- [x] Persist only resolved state/manifest version and credentials in named volumes. On rerun reconcile fixture IDs and restore missing fixture files/entries; never delete unrelated entries as part of seed. Handle import exclusions deliberately when restoring previously deleted fixtures.
- [x] Run offline tests, then `docker compose -p excludarr-dev run --rm tools seed --arr-only` twice. Verify stable counts/IDs and actual imported file presence on both runs.

### Task 3: Plex, Tautulli and Seerr fixtures

**Files:** dev/stack.py, dev/history.py, tests/test_dev_stack.py, tests/test_dev_history.py.

**Interfaces:** `seed_plex(arr_state: dict) -> dict` resolves test libraries, GUIDs and
rating keys; `build_history(path: Path, state: dict, now: datetime) -> None` creates a
standalone compatible import database; `seed_tautulli(plex_state: dict) -> None`;
`seed_seerr(arr_state: dict) -> dict`. Full `seed()` returns success only after readback.

- [x] Test missing/expired auth produces local setup instructions with no secret; ambiguous/unmatched Plex GUID prevents full readiness; history fixture preserves resolved movie/show/episode keys and test user; unsupported schema fails clearly; second import/request seed does not duplicate rows. Assert recent/old timestamps relative to an injected UTC clock and no-history controls remain absent.
- [x] Run targeted tests and confirm failures.
- [x] Document/implement one-time test-account claim and Tautulli/Seerr login steps using verified service APIs where supported; do not bypass account auth. Create Plex libraries using shared fixture paths and wait for matching IDs. Verify only the expected test server identity.
- [x] Inspect the pinned Tautulli schema/source and build the smallest accepted history import fixture. Import through its documented API, wait for completion and assert `get_history` returns the intended users/keys/watched facts. Use a fixture marker/actual readback for idempotence; never write a live Tautulli database directly.
- [x] Create/read back Seerr movie and TV requests through its API with no download/search clients configured. Keep required fixture requests eligible for request cleanup tests; reuse existing matching requests on reseed.
- [x] Run offline tests. After the user's local authentication, run full seed twice and verify stable history/request counts and proper Plex GUIDs. If authentication is pending, report this step pending and retain working Arr-only setup; no substituted mocks or full-suite success claim.

### Task 4: Real scenario configurations and integration checks

**Files:** dev/stack.py, dev/checks.py, tests/test_dev_stack.py.

**Interfaces:** `write_configs(state: dict, directory: Path) -> None` writes validated
preview/action/daemon YAML; `run_checks(*, arr_only: bool = False) -> list[dict]` returns
`{name, status, detail}` records (passed/failed/skipped); `check` exits nonzero on failure
or missing required full setup, and labels deliberate Arr-only omissions as skipped.

- [x] Test generated YAML loads through production config validation, default rules preview, action rules select fixture tags/IDs, preview database differs from action/daemon database, and check refuses mismatched server identities before invoking CLI/actions. Assert failure output is sanitized and optional checks are never silently counted as passed.
- [x] Run targeted tests and confirm failures.
- [x] Implement configuration generation and checks using the existing CLI/core, not duplicated action implementations. Verify preview leaves all service/file state unchanged; monitor/unmonitor, tag, delete_files, delete with import exclusion, supported Sonarr season/episode scopes, protected controls, grace enqueue/rescue, Plex Leaving Soon add/remove/refresh and Seerr cleanup. Scope every action to fixture subjects and compare actual API state/files after each step. Restore affected fixtures for repeat runs.
- [x] Use a local StevenLu-format feed with complete identifiers supported by the current reader. Implement scheduled publication/auth/status checks and a bounded blocked-source daemon scenario to check HTTP responsiveness, manual lock refusal, and clean shutdown. Do not introduce a production source or change scheduler semantics; use development-only fixture controls for blocking. Test same-database contention via the real CLI processes.
- [x] Run Arr-only real checks, reseed, and repeat. After local auth run full checks, reseed, and repeat; retain concrete results and any external-service blockers. Validate both a successful and an invalid feed API key and actual file deletion, not merely CLI exit codes.

### Task 5: Developer guide and final verification

**Files:** .github/DEVELOPER.md, README.md, docs/superpowers/plans/2026-11-11-development-stack.md.

**Interfaces:** Document the exact startup/claim/seed/status/preview/action/daemon/check/reseed/reset commands implemented above; no extra wrapper framework.

- [x] Replace the old manual empty-Arr instructions with the new workflow, port table, credential lifecycle, fixture/scenario matrix, expected results and optional live-provider checks. Explain daemon's per-rule preview semantics, network requirements, imported-history limitations and setup requiring user login.
- [x] Document `docker compose -p excludarr-dev down --volumes` as an explicit full reset of this project only; distinguish reseed from reset and explain that reset loses Plex setup. Explain how to stop the daemon before reseed and which commands perform actual fixture deletions.
- [x] Run `.venv/bin/ruff check src tests dev`, `.venv/bin/ruff format --check src tests dev`, `.venv/bin/pytest -q`, Compose config rendering and local builds. Check Docker mounts/ports and repository diff for accidental credentials and unrelated changes.
- [x] Exercise the guide from a clean development project where practical; perform reseed after destructive checks. Record commands/results and pending login-dependent checks without marking them complete.
- [x] Request one independent final review, fix substantive findings with appropriate checks, then summarize changed files, real integration coverage and remaining limits. No commit, push, merge or production deployment.

## Plan Self-Review

The five tasks cover isolation/lifecycle, Arr fixtures, authenticated companion fixtures,
real action/scheduler checks and documentation. Review Focus cases are pinned to task
tests. Shared signatures and generated config paths agree across tasks. Cloud providers
remain explicitly optional; no account-dependent result may be inferred from container
health or offline unit tests. Implementation-time API/schema investigation is required
against the pinned images, with bounded failures rather than mocked fallback.

## Execution result

- All five real service containers run with isolated volumes and localhost ports.
  Tautulli/Seerr config volumes use `nocopy` to avoid copied image warning markers;
  persistence was verified across recreation without changing credentials or settings.
- `setup-plex` creates libraries after claim, before companion wizards. Full authenticated
  Plex GUID/episode matching and Tautulli movie/episode history import/readback succeeded.
- Seerr Radarr/Sonarr connections were configured through its API and tested with searches
  disabled. Request seeding encodes title searches, resets only fixture availability when
  necessary and reads back newly created requests; reruns reuse existing requests.
- Full real integration checks passed after authentication: actions, queue/rescue/expiry,
  Plex Leaving Soon, Seerr cleanup, Tautulli rules, protected controls, HTTP/auth/locks,
  graceful daemon shutdown and actual cron feed/rule jobs. Repeated seed/check/restoration
  evidence is recorded in the plan ledger.
- Offline suite after fixes: 472 passed. Ruff, format, Compose rendering and image builds
  passed. Independent review completed and Important findings fixed with RED→GREEN tests.
- Cloud provider catalog/watchlist checks remain optional and were not run. No commits,
  push, merge or production changes. The normal daemon is left stopped; fixtures restored.
