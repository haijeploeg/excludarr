# Daemon and Scheduler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Run per-list/per-rule cron schedules and the existing feed server in one persistent process without overlapping mutations.

**Architecture:** A pure planner calculates due work, a single worker invokes the existing core, and a supervisor keeps HTTP and heartbeat updates responsive. Native file locks serialize daemon/manual execution; SQLite records job outcomes for CLI status and a later UI.

**Tech Stack:** Python >=3.12, existing Typer/httpx/Pydantic/SQLAlchemy stack, croniter >=6.0,<7, filelock >=3.16,<4 and tzdata >=2024.1. No job framework or subprocess executor.

**Spec:** `docs/superpowers/specs/2026-11-11-daemon-scheduler-design.md` (user approved).

## Global Constraints

- No commits, pushes, releases or branch changes without user authorization. At execution time, arrange isolation/featurebranch according to repository instructions; the current branch belongs to the deployed list proxy.
- English code, CLI and documentation; Dutch conversation.
- Optional schedule per rule/list; no schedule means manual-only; disabled rules never schedule.
- Five-field cron, central IANA timezone default UTC, no sub-minute jobs or custom parser.
- One worker; preserve ordered rule batches, preview/grace/rescue and all existing list semantics.
- No destructive startup/offline replay; bootstrap only scheduled feeds with unusable snapshots.
- HTTP stays responsive during work; errors do not kill subsequent scheduling.
- Daemon requires local file-backed SQLite; existing manual CLI database support remains unchanged.
- Keep serve, one-shot commands and legacy cron; no UI, Helm, notifications or hot reload.

## File Structure

- `scheduling.py`: strict cron validation, timezone-aware occurrence calculation and `SchedulerConfig`; independent of Config to avoid import cycles.
- `jobs.py`: immutable job descriptions and deterministic planner state; no database, networking, sleeping or signal handling.
- `locking.py`: native singleton/execution locks keyed by canonical SQLite path; clear busy errors.
- `execution.py`: lock-protected adapters for existing engine/list services. It never renders output or starts threads.
- `daemon.py`: supervisor, serial worker, bootstrap/recovery, job outcome classification and orderly shutdown.
- Existing `config.py`, `list_config.py`: optional scheduling fields; `engine.py`: subset and lifecycle hooks; clients/facts: resource cleanup.
- Existing storage models/repo plus migration `0005_scheduler.py`: daemon/job state and compact execution records.
- Existing CLI/reporting/output: daemon command, schedule status and shared endpoint presentation.
- Tests: focused `test_scheduling.py`, `test_jobs.py`, `test_locking.py`, `test_execution.py`, `test_scheduler_repo.py`, `test_daemon.py`, `test_daemon_commands.py`; extend connected existing tests.

## Review Focus

1. DST/backward clock jumps must not repeat destructive occurrences or move nonexistent wall times to another time (Tasks 1, 5).
2. Symlink/relative database paths and independent processes must share the same native lock; stale heartbeat must never grant ownership (Tasks 2, 6).
3. A rule error after earlier rules finish must preserve partial outcomes and leave only not-started rules pending (Tasks 4, 6).
4. Adding default schedule=None or editing timing must not invalidate old feed fingerprints or remove unrelated queue entries (Tasks 1, 4).
5. Stop requests, occupied execution locks and slow HTTP calls must not start further work, lose pending jobs or block feed/status responsiveness (Tasks 5–7).

---

### Task 1: Cron contract, timezone config and snapshot compatibility

**Files:** Create `src/excludarr/scheduling.py`, `tests/test_scheduling.py`; modify `pyproject.toml`, `config.py`, `list_config.py`, `lists/service.py`; extend config/snapshot tests.

**Interfaces:**
- `validate_schedule(value: str | None) -> str | None`: normalized five-field text or ValueError with no input echo. Expose `Schedule = Annotated[str | None, PlainValidator(validate_schedule)]` for both models; default None.
- `next_occurrence(expression: str, after: datetime, timezone: str) -> datetime`: aware UTC, strictly after the supplied UTC instant; spec DST policies.
- `SchedulerConfig(BaseModel)`: `timezone: str = 'UTC'`, forbid extras, validate ZoneInfo availability.
- `Config.scheduler: SchedulerConfig`; `Rule.schedule: Schedule`; `ProxyList.schedule: Schedule`.

- [x] Write `test_cron_validation` for steps/ranges/names/Sunday 0 and 7, OR day semantics, invalid timezone, impossible `0 0 30 2 *`, six/seven fields, @reboot and unsupported L/W/#/H/R extensions. Reject booleans/nonstrings. Literal occurrence assertions:
  ```python
  assert next_occurrence('0 2 * * *', utc('2026-11-11T00:00:00Z'), 'Europe/Amsterdam') == utc('2026-11-11T01:00:00Z')
  assert next_occurrence('30 2 * * *', utc('2026-03-29T00:00:00Z'), 'Europe/Amsterdam') == utc('2026-03-30T00:30:00Z')
  assert next_occurrence('30 2 * * *', utc('2026-10-25T00:00:00Z'), 'Europe/Amsterdam') == utc('2026-10-25T00:30:00Z')
  assert next_occurrence('30 2 * * *', utc('2026-10-25T00:45:00Z'), 'Europe/Amsterdam') == utc('2026-10-26T01:30:00Z')
  ```
  `utc` is a small test helper parsing aware ISO strings. Also test starting during the second autumn fold.
- [x] Run `.venv/bin/pytest -q tests/test_scheduling.py`; require RED for missing behavior. Install the declared dependencies into the existing venv at execution time, without changing package versions/releases elsewhere.
- [x] Implement occurrence calculation through croniter over naive local wall candidates, then attach ZoneInfo fold=0 and validate by UTC round-trip. Skip nonexistent candidates and candidates not strictly after `after`; never use naive datetime comparisons for deadlines. This fixes DST policy without implementing cron parsing. Restrict supported token/name vocabulary before delegating grammar to croniter. Bound impossible-expression search to a Gregorian 400-year cycle using the library's search limit.
- [x] Add config tests proving legacy defaults, library-only configs, disabled rules and explicit schedules parse. Exclude only ProxyList.schedule from fingerprint canonicalization; do not change the content fingerprint revision. Capture a literal pre-change fingerprint from the existing minimal fixture before editing and assert it remains identical with absent/None/changed schedule and timezone, while filter edits still invalidate it.
- [x] Run `.venv/bin/pytest -q tests/test_scheduling.py tests/test_config.py tests/test_list_config.py tests/test_list_snapshots.py`; require PASS. Keep `config validate` aware of cron/timezone errors without requiring daemon startup.

### Task 2: Cross-process locking

**Files:** Create `src/excludarr/locking.py`, `tests/test_locking.py`; dependency declared in Task 1.

**Interfaces:**
- `sqlite_path(url: str) -> Path | None`: use SQLAlchemy URL parsing; canonical absolute filename resolving symlinks. Return None for memory/non-SQLite/SQLite URI forms unsuitable for daemon native-file locking.
- `require_daemon_database(url: str) -> Path`: ConfigError for unsupported database forms.
- `WorkBusy(ConfigError)` identifies occupied execution lock without leaking config.
- `execution_lock(url: str) -> ContextManager[None]`: nonblocking native lock at `<db>.execution.lock`; no-op for existing CLI-only database forms returning None. Unsupported native-lock platforms fail clearly rather than using expiring/cooperative marker locks.
- `daemon_lock(url: str) -> ContextManager[None]`: mandatory native lock at `<db>.daemon.lock`, nonblocking; OS release is authoritative. Never delete lock files while another process may reference their inode.

- [x] Write real-process tests using Events/Pipes, not timing sleeps: two owners of the same lock conflict, release/crash permits acquisition, a held execution lock raises WorkBusy, relative/symlink aliases conflict, daemon lock rejects second process and memory/PostgreSQL URL. Assert an existing manual memory-backed engine test remains usable.
- [x] Run `.venv/bin/pytest -q tests/test_locking.py`; confirm RED.
- [x] Implement FileLock acquisition with timeout=0. Require native Unix/Windows backend, rejecting SoftFileLock fallback. Catch only the library's Timeout as contention; report filesystem permission errors separately. Keep an owned lock object alive for the full context. Construct separate lock objects for independent attempts so reentrancy cannot defeat worker/manual exclusion.
- [x] Run `.venv/bin/pytest -q tests/test_locking.py tests/test_repo.py`; require PASS, including subprocess exit cleanup.

### Task 3: Scheduler state, execution records and recovery storage

**Files:** Modify `storage/models.py`, `storage/repo.py`; create migration `storage/migrations/versions/0005_scheduler.py`, `tests/test_scheduler_repo.py`.

**Interfaces:**
- `JobKey = tuple[Literal['list','rule'], str]` and frozen `JobSpec(key: JobKey, schedule: str, order: int)` in `jobs.py` (type declarations only here).
- Add `daemon_state`: singleton ID, instance UUID, start/heartbeat/stop UTC timestamps, configured timezone. Add `scheduled_job`: composite kind/name PK, current instance, schedule, next_due/pending_due, state (idle/pending/running), last_dispatched_due. Add `job_execution`: integer PK, instance, kind/name, scheduled/start/finish timestamps, outcome, sanitized error and JSON summary.
- Repo methods: `scheduler_start(instance: str, jobs: list[JobSpec], timezone: str, at: datetime) -> None`; `scheduler_heartbeat(instance: str, at: datetime) -> None`; `scheduler_stop(instance: str, at: datetime) -> None`; `scheduler_update(instance: str, jobs: list[dict]) -> None`; `job_start(instance: str, key: JobKey, due: datetime, at: datetime) -> int`; `job_finish(instance: str, run_id: int, outcome: str, summary: dict, error: str | None, at: datetime) -> None`; `scheduler_status() -> dict`; `job_watermarks() -> dict[JobKey, datetime]`.
- Status returns detached dictionaries/dataclasses, never Sessions/ORM entities. UTCDateTime is reused. Mutating methods guard writes by current instance ID.

- [x] Write repo tests for rule/list name collisions, UTC round-trips, heartbeat independent of running jobs, atomic job completion, renamed/removed job reconciliation, and guarded old-instance writes. Under a newly acquired singleton, startup marks prior unfinished runs interrupted, clears old pending state, retains watermarks/outcomes for unchanged keys and creates no external actions.
- [x] Run `.venv/bin/pytest -q tests/test_scheduler_repo.py`; confirm RED.
- [x] Implement migration and short per-method transactions. `scheduler_start` is called only under the OS singleton lock; it may reconcile job rows but never touches queue/history/cache/feed data. Persist compact outcome/counts only; existing history/snapshots hold detailed evidence. No retention/cleanup feature in this task.
- [x] Upgrade a database explicitly migrated to 0004 containing queue/history/cache/snapshots. Assert old rows and stored fingerprints survive. Run `.venv/bin/pytest -q tests/test_scheduler_repo.py tests/test_repo.py tests/test_list_snapshots.py`; require PASS.

### Task 4: Ordered engine subset and shared execution boundaries

**Files:** Create `execution.py`, `tests/test_execution.py`; modify `engine.py`, `clients/http.py`, `facts.py`, CLI invocation points; extend `tests/test_engine.py`, client/CLI tests.

**Interfaces:**
- Extend `engine.run` with `rule_names: frozenset[str] | None = None`, `should_stop: Callable[[], bool] = lambda: False`, `on_rule_start: Callable[[Rule], None] | None = None`, `on_rule_complete: Callable[[RuleReport], None] | None = None`. Preserve all existing parameters. Existing rule_filter and rule_names intersect if both supplied; never filter Config itself.
- Hooks run after shared preflight: start before per-rule prefetch/evaluation; complete only after that rule fully finishes, including preview/no-match/immediate/grace paths. An exception omits complete for that active rule. Existing on_report retains its current timing/partial-report behavior. Check should_stop between rules, including before the first.
- `execute_rules(ctx: Context, *, dry_run: bool, on_acquired: Callable[[], None] | None = None, **kwargs) -> list[RuleReport]` in execution.py acquires execution_lock only for dry_run=False and delegates all engine arguments/hooks unchanged.
- `execute_feed(config: Config, slug: str, repo: Repo, now: datetime, *, publish: bool = True, on_acquired: Callable[[], None] | None = None) -> dict` acquires execution_lock only for publish=True and delegates to existing refresh_list. No nested locks in engine/list core. Both adapters call on_acquired only after successful lock acquisition, before delegating; a busy adapter never starts a job record. Preview delegates without a mutation lock.
- `HttpClient.close() -> None`, `Clients.close() -> None`: close owned integration HTTP clients. The daemon owns fresh Clients per batch and closes them in finally; manual CLI _report also closes its owned clients after rendering-related requests finish.

- [x] Write engine tests asserting due subset runs in YAML order despite unordered input names, shares inventory/removal tracking, and retains unscheduled rules' grace entries. Test stop before first/between rules, all completion paths, preflight failure before starts and exception in an active rule with previous completed report retained.
- [x] Write lock-boundary tests: manual run/refresh cannot mutate while the execution lock is held; preview/read paths remain usable; Context clients close after success/failure. Use real shared services/Repo and fake external clients, not assertions solely on mock calls.
- [x] Run new/extended tests and observe RED, then implement these hooks and replace only CLI's engine.run/refresh_list invocation with the execution adapters. Retain existing interactive confirmation, output/error boundaries, callbacks and partial structured reports. WorkBusy aborts manual refresh promptly rather than continuing through every name during contention.
- [x] Run `.venv/bin/pytest -q tests/test_execution.py tests/test_engine.py tests/test_cli_commands.py tests/test_list_commands.py tests/clients/test_http.py`; require PASS.

### Task 5: Deterministic planner and cron coalescing

**Files:** Complete `jobs.py`; create `tests/test_jobs.py`.

**Interfaces:**
- `configured_jobs(config: Config) -> list[JobSpec]`: scheduled lists in mapping order, scheduled enabled rules in YAML order; namespaces remain distinct.
- Frozen `PendingJob(key: JobKey, due: datetime)`.
- `Planner(jobs: list[JobSpec], timezone: str, started_at: datetime, watermarks: dict[JobKey, datetime])` calculates next future occurrences from max(started_at, watermark).
- `bootstrap(key: JobKey, at: datetime) -> None`; `poll(now: datetime) -> None`; `take_batch(now: datetime) -> list[PendingJob]`; `release(jobs: list[PendingJob]) -> None`; `start(key: JobKey) -> None`; `complete(key: JobKey, at: datetime) -> None`; `snapshot() -> list[dict]`.
- take_batch reserves either one earliest due list or all earliest-minute rule ties in YAML order. Reserved jobs have no second pending entry; release restores the original due timestamp without advancing a watermark. Complete advances the dispatched watermark and calculates next future time from max(completion time, due). Reservation is internal: a reserved, not-yet-started rule remains pending in snapshot output until start(key) is called by the execution hook. snapshot dictionaries use kind/name/schedule/next_due/pending_due/state/last_dispatched_due keys matching Task 3 storage. These pure methods never run jobs or sleep.

- [x] Write tests with literal timestamps and these assertions:
  ```python
  assert [job.key for job in batch] == [('rule', 'A'), ('rule', 'B')]
  assert len(planner.snapshot()) == 2  # jobs, never one row per missed minute
  assert pending_due_after_busy == original_due
  assert next_due_after_long_run > finished_at
  ```
  Use explicit scenarios: restart at 10:37 yields next hourly 11:00, not 10:00; cron B 10:00/list 10:01/A 10:02 dispatches B→list→A even with A first in YAML; A/B same minute run A→B; list/rule same minute runs list first. Include lock-contention release, multiple missed minutes, active occurrences skipped, backward jump after completion/restart, DST fold, disabled/manual-only jobs and separate list/rule identities.
- [x] Run `.venv/bin/pytest -q tests/test_jobs.py`; confirm RED.
- [x] Implement minimal planner over a mapping keyed by JobKey, using next_occurrence from Task 1. Retain the first overdue timestamp; do not append an occurrence queue or enqueue catch-up on startup. Reserve/release lets execution-lock contention avoid losing work before any run starts.
- [x] Run `.venv/bin/pytest -q tests/test_jobs.py tests/test_scheduling.py`; require PASS.

### Task 6: Daemon worker, outcomes, bootstrap and shutdown

**Files:** Create `daemon.py`, `tests/test_daemon.py`; consume Tasks 1–5 and existing list server/reporting.

**Interfaces:**
- `run_daemon(config: Config, repo: Repo, *, host: str, port: int, stop: Event, now: Callable[[], datetime] = utc_now) -> None`: supervisor; caller already holds daemon_lock. Bind HTTP before dispatch, create planner/reconcile DB, run one serial worker, heartbeat independently and close everything on exit.
- `execute_batch(config: Config, repo: Repo, instance: str, jobs: list[PendingJob], stop: Event, now: Callable[[], datetime]) -> BatchResult`; BatchResult has completed keys/outcomes plus unstarted PendingJobs to release. WorkBusy releases the whole batch with no failed execution record. A feed starts its record through on_acquired. A rule batch captures its actual acquisition time there, starts individual records through on_rule_start, and finishes through on_rule_complete. A preflight error with no start hooks records failed executions for the selected jobs using that acquisition time; never infer job starts from on_report. Unexpected job exceptions are sanitized/recorded; fatal storage/supervisor failures stop dispatch and exit nonzero.
- Runtime interval decisions: supervisor/worker waits use Event.wait with at most one second latency; heartbeat every five monotonic seconds; CLI marks heartbeat older than 15 seconds as stale/unknown. No sleep-based tests. Monotonic cadence handles wall-clock changes; aware UTC now supplies business timestamps.

- [x] Write tests with controlled clock/events for expired/missing/incompatible scheduled-feed bootstrap, no warm refresh for valid/unscheduled feeds, and no startup library actions/backfill. Ensure HTTP binds before any task, bind errors start no tasks, library-only mode opens no listener, empty/no-server daemon is rejected.
- [x] Cover a successful preview rule (no mutation), grace eligibility only on scheduled evaluation, rescue preservation, failed ActionResult despite normal return, side-effect warning, feed unknown-excluded warning, missing-export-ID feed success, integration failure and sanitized unexpected exception followed by another successful job.
- [x] Test mid-batch failure: A success, B failure, C not started → A remains success, B failed, C released once with its old due timestamp. Preflight failure before A → entire batch failed/rescheduled, no repeated immediate retry. Map report timing through Task 4 hooks rather than assuming on_report means finished.
- [x] Test blocked execution while HTTP and heartbeat remain responsive, manual execution lock contention retaining pending jobs, a stop event before dispatch/between rules/during an active action, and clients closing after exceptions. Signal termination does not artificially cancel the active request. Use bounded test synchronization timeouts so failures cannot hang the suite.
- [x] Run `.venv/bin/pytest -q tests/test_daemon.py`; confirm RED; implement orchestrator and classify outcomes using existing reports: failed action → failed; side-effect/queue warnings or blocked unknown feed decisions → warning; preview-only normal completion → success. Persist scheduled/start/finish separately. Mark no-not-started job successful.
- [x] Keep snapshot serving in its own thread and stop it only after worker completion. Drain no pending jobs on shutdown. Persist stop state, release resources on failure, and sanitize messages against all configured credentials; no config objects/raw tracebacks containing credentials in logs. Log sanitized exception class/stage for programming failures.
- [x] Run `.venv/bin/pytest -q tests/test_daemon.py tests/test_jobs.py tests/test_execution.py tests/test_scheduler_repo.py tests/test_list_server.py`; require PASS.

### Task 7: CLI startup/status and configuration diagnostics

**Files:** Modify `cli.py`, `reporting.py`, `output.py`; create `tests/test_daemon_commands.py`; extend existing config/serve tests.

**Interfaces:**
- `daemon --host 127.0.0.1 --port 8989`: validate config/local DB before startup, acquire singleton before Repo migration, register SIGINT/SIGTERM handlers that only set Event, then call run_daemon. Restore signal handlers on exit. No prompts or implicit preview changes.
- `schedule status [-o table|json|yaml]`: use current config plus Repo.scheduler_status, no Clients/integration calls; display daemon offline/stale/active, schedule timezone/cron, next run, pending/running state and last outcome/error. An offline calculation may be labeled hypothetical, never active; simplest is next_run=None when offline.
- Shared endpoint presentation helper in output.py for serve/daemon so actual feed URL/credential placeholder behavior remains identical. No general HTTP framework or new routes.
- Shared scheduling warning: compare the next two actual occurrences per scheduled list at config validation/startup and warn when the gap is >= six hours. This is an advisory bounded check, not a guarantee over every future calendar gap. Leave config accepted; document that bound.

- [x] Write CLI tests for library-only/list-only/mixed/empty modes, startup schedule/endpoint text, no keys in any output, busy/failing bind/database errors, invalid cron/timezone config reporting, offline status with no rows, stale heartbeat with an actually held OS lock, job names shared across rule/list, DST-offset table times and one JSON/YAML document with correct timestamps.
- [x] Run `.venv/bin/pytest -q tests/test_daemon_commands.py`; confirm RED, then implement the thin CLI/reporting layer. Status reads must not acquire ownership, mark interrupted runs or perform migrations per HTTP request. Preserve existing serve's read-only behavior and standalone commands.
- [x] Check status/startup warning text at 80 and 120 columns with Rich console fixtures; paths/names must wrap rather than lose identifying information.
- [x] Run `.venv/bin/pytest -q tests/test_daemon_commands.py tests/test_cli_commands.py tests/test_list_commands.py tests/test_config.py`; require PASS.

### Task 8: One-container deployment, documentation and final checks

**Files:** Create `docs/daemon.md`, `.examples/daemon-example.yml`, `.examples/daemon-compose.yml`; modify README, `docs/list-proxy.md`, `.github/DEVELOPER.md`, AGENTS.md architecture map and `tests/test_example_config.py`. Keep entrypoint.sh and existing cron examples unchanged unless an observed compatibility failure requires a minimal fix.

- [x] Add a complete English sample with timezone Europe/Amsterdam, hourly scheduled feeds and a daily preview=true library rule. The Compose sample uses `command: [daemon, --host, 0.0.0.0]`, CRON_MODE=false, persistent /config and `stop_grace_period: 5m`; users may increase it for slower jobs. Match the existing .env/secret substitution model and keep endpoints authenticated.
- [x] Explain one replica, native local-file SQLite locking, no concurrent old cron/refresh container, warm scheduled feeds versus manual-only feeds, no offline replay, next-rule grace execution, per-rule preview flags, timezone/DST, config restart, status outcomes and manual mutation contention. Explain friendly UI controls are future work with advanced cron retained.
- [x] Document migration: stop old server/refresh jobs, preserve config/database, add chosen schedules, switch to daemon command, then verify schedule status/feed URLs. Do not change live user deployments as part of the implementation.
- [x] Add example-loading coverage with dummy env values and validate Compose in a temporary directory. Run:
  ```bash
  .venv/bin/pytest -q
  .venv/bin/ruff check src tests
  .venv/bin/ruff format --check src tests
  git diff --check
  docker build -t excludarr:dev .
  docker run --rm excludarr:dev daemon --help
  ```
  Require all PASS. Confirm the wheel/image contains migration 0005 and named timezone data.
- [x] Perform a bounded container lifecycle smoke with temporary config/database and preview-only/fake integration work: HTTP available, second daemon rejected, SIGTERM after a blocked fake execution finishes, next pending job not started, process exits within chosen grace. Make no live destructive requests. If Docker/socket permissions block it, record that exact unverified check rather than claiming success.
- [x] Request one independent whole-change review focused on the five Review Focus cases after all tests pass. Fix important findings with reproducing regressions, run appropriate checks, and leave the branch uncommitted unless the user explicitly authorizes commits.

## Self-review and implementation rulings

Spec coverage: cron/config/fingerprint → Task 1; native exclusion → Task 2;
status/recovery/migrations → Task 3; engine/CLI reuse and cleanup → Task 4;
ordering/coalescing/DST watermarks → Task 5; bootstrap/failure/shutdown → Task 6;
CLI/status/diagnostics → Task 7; docs/deployment/whole-suite smoke → Task 8.
All consumed interfaces are defined earlier; interfaces can be implemented without
copying the old CLI engine/reporting logic. Each review-focus risk has owning tests.

Builder choices now fixed by this plan:
- croniter >=6.0,<7 supplies recurrence grammar, with explicit wall-time DST policy;
  filelock >=3.16,<4 supplies native cross-platform OS locks; tzdata supplies zones.
- One-second bounded waits, five-second independent heartbeat, 15-second stale
  status; stale heartbeat never overrides a native lock.
- Lock adapters live outside raw engine/list functions; both CLI and daemon use
  them, avoiding nested ownership and preserving direct unit-test core calls.
- Existing CLI-only non-file databases retain behavior; daemon mode rejects them.
- Six-hour gap warning examines the next two occurrences only, keeping startup
  bounded; normal six-hour expiry remains authoritative.

Primary API references checked while planning:
- https://github.com/pallets-eco/croniter/blob/main/README.rst
- https://py-filelock.readthedocs.io/en/latest/
- https://docs.python.org/3/library/zoneinfo.html

No product code, dependency installation, live job execution or commits are part
of this planning step.

## Implementation result

Implemented on user-provided `feat/daemon`, without commits or deployment changes.
The independent whole-change review found two important issues, both reproduced
and fixed: file-backed SQLite URL connection options bypassed locking; Leaving
Soon queue updates lost their warnings. File/URI aliases now share native locks
while daemon database eligibility remains separate. Core collection warnings flow
through CLI/JSON and daemon outcomes with shared credential redaction.

Native real-process lock tests use subprocess pipes because multiprocessing
semaphore setup hung in the macOS sandbox; production locking is unaffected.
The implementation retains the approved limits: one local SQLite deployment,
unbounded historical job records, and a six-hour warning checking the next two
occurrences rather than all future calendar gaps.

Verification: 442 tests passed; Ruff check/format, whitespace, docs/example/Compose
validation and Docker build. Container smoke uses only fake data: HTTP/heartbeat
while blocked, pending rule retention, second-daemon exclusion, SIGTERM drain,
packaged timezone/migration and final-image query-option lock regression. No live
library actions were performed; real integration calibration and the pre-existing
Plex collection payload uncertainty remain outside this verification.
