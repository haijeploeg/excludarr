# Seeded development stack

## Intent and decisions

Provide a disposable local environment for developing and manually exercising Excludarr
against real Radarr, Sonarr, Plex, Tautulli and Seerr instances. The user wants the full
suite, generated media and preseeded scenarios so autonomous daemon actions never need
to target their personal library. They will create a separate Plex test account and
accept a one-time login. Conversation and operational help are Dutch; repository
artifacts are English. No commits without a request.

## Approaches

- Empty real services with manual setup: the existing root Compose file does this for
  Radarr/Sonarr; it does not provide repeatable test data or verify the integration chain.
- Mock services: useful in the existing unit suite, but cannot validate real imports,
  file deletion, Plex collection requests or Seerr cleanup.
- **Chosen: real services with scripted fixtures and a one-time Plex account setup.**
  This matches the user's full-suite request. Keep cloud authentication and metadata
  dependencies explicit rather than claiming the stack is offline or unattended.

## Scope and isolation

Replace the existing development-only root `docker-compose.yml`, update
`.github/DEVELOPER.md`, and add a small `dev/` directory containing seed tooling,
fixture manifest, development image as needed and scenario configurations. Link the
guide from README. Reuse the application image and existing configuration vocabulary;
do not change the engine to accommodate fixtures.

Use one dedicated Compose project, project-scoped named volumes, a bridge network,
and distinct host ports bound only to 127.0.0.1. No fixed container names, production
config mounts, Docker socket, host networking or production credentials. Service
addresses in generated Excludarr config are fixed Compose DNS names. Generated secrets
and Plex credentials stay in disposable volumes or a gitignored development env file,
never committed or printed. Reset commands are scoped explicitly to this project.
Validate the expected test server identities and seed marker before destructive checks;
never accept arbitrary endpoint overrides in the test runner.

The builder selects compatible pinned image versions/digests with ARM64 support and
records them. Outbound access is needed for images, Plex authentication and metadata
matching (including Arr metadata services and Seerr/TMDB). JustWatch availability and
external list providers remain live optional checks, not seeded deterministic facts.
No indexers or download clients are configured and no copyrighted media is downloaded.

## Startup and seed lifecycle

1. Start real service containers, local Excludarr build and a one-shot seed tool.
   Excludarr daemon execution is opt-in after seeding, never races initialization.
2. Bootstrap Arr API keys, root folders and suitable existing quality profiles. Generate
   a small valid video/audio test clip with FFmpeg in the development tooling image.
   Copy it into conventional movie/episode paths with known stable metadata IDs.
3. Add movie and series metadata through real Arr APIs without automatic searches;
   import/rescan the generated files. Resolve actual IDs from API responses rather
   than assuming database IDs or quality profile numbers.
4. Guide the user through claiming only the new Plex server with their test account,
   and initial authentication of Tautulli/Seerr when required. Never ask for credentials
   in chat. The guide distinguishes temporary Plex claim tokens from persistent tokens.
   Commands detect incomplete authentication and report the exact next local setup step.
5. Create movie/TV Plex libraries for the shared generated media, scan/match them, and
   wait for stable TMDB/TVDB GUIDs. Verify matched IDs before enabling related checks.
6. Seed Tautulli history using its documented `import_database` API with a generated
   fixture matching the pinned schema and actual Plex rating keys/test user. Import
   only after validating this is the test server. Do not edit a running service's SQLite
   database directly. Verify both recent/old watch history via its real `get_history` API.
7. Create Seerr requests via its API, with approval/search behavior controlled so no
   downloads occur. Resolve actual media/request IDs and verify them by reading back.
8. Produce Excludarr configs and a concise readiness/scenario report with localhost
   URLs, seeded item names and expected outcomes; never expose tokens in the report.

Seeding is repeatable without duplicate media/requests/history or resetting account
setup. Use a manifest/version marker and deterministic fixture identities. After
destructive tests, reseed restores missing fixture data. Full reset intentionally drops
only this project's data volumes and consequently requires Plex setup again. Partial
failures retain completed steps and provide a useful error; readiness is not reported
until actual service data has been read back successfully.

## Scenarios and user workflow

Ship a small fixed fixture set (builder chooses titles and tag names) covering movies,
series, seasons and episodes; monitored/unmonitored; present/missing files; recent/old/
absent watch history; requested/unrequested; and a protected control item. Each action
scenario uses separate fixture items where possible so tests do not destroy later tests.

Default config has preview rules and a separate state database. An explicit disposable
action config enables real mutations; examples show preview, direct run, daemon,
queue/rescue and reset/reseed. Active rules are narrowly scoped to fixture tags/IDs.
Exercise delete, delete_files, monitor/unmonitor, tags, import exclusions, short grace
queue and rescue, Plex Leaving Soon membership/refresh and Seerr request cleanup.
Verify expected API state AND generated file presence, including protected controls.
Respect actual supported action/target combinations in the binding engine spec.

Include scheduled fixture rules and a local deterministic feed source using an existing
source format, served only inside the dev network. Exercise list publication, auth,
HTTP availability during work, status and manual/daemon lock contention. Real external
Popular/Trending/saved/watchlist providers are separately documented optional smoke
checks requiring test-account credentials; do not mutate a personal cloud watchlist.
No new production list source or mocked integration client is introduced.

Provide one explicit integration-check command, separate from default pytest, that
performs and verifies destructive actions only in this stack. It must fail clearly if
credentials/setup are missing or expected external metadata cannot be resolved. Its
output distinguishes passed, failed and skipped optional checks; healthy containers do
not imply that all integration scenarios passed. Do not claim every feature is covered:
document the concrete scenario matrix and remaining gaps.

## Verification and non-goals

Keep unit tests offline; add small tests for nontrivial seed validation/idempotence and
check Compose rendering. Build/start the full local suite, seed it and run available
real integration scenarios, including a reseed after destructive actions. User-owned
Plex authentication may delay the full chain: validate the Arr portion independently,
report outstanding checks and resume after local authentication, without substituting
mocks or calling the entire suite verified. Run existing lint/tests for regressions.

No production deployment, UI, general orchestration framework, download automation,
media playback client, distributed runner or changes to daemon preview semantics.
Cloud availability, playback capture, arbitrary provider catalogs and account creation
are not guaranteed by imported fixtures. Fixture schema compatibility is checked against
pinned Tautulli versions; upgrades require revalidation rather than silent fallback.

## Primary references

- [Plex container claim and networking](https://docs.linuxserver.io/images/docker-plex/)
- [Tautulli API: history and database import](https://docs.tautulli.com/extending-tautulli/api-reference)
- [Seerr Plex authentication](https://docs.seerr.dev/api/sign-in-using-a-plex-token/)
- [Seerr request creation](https://docs.seerr.dev/api/create-new-request/)
