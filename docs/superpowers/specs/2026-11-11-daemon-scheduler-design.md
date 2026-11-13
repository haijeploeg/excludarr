# Daemon and per-item scheduling

Status: approved by the user · 2026-11-11.

## Intent and agreed scope

Run Excludarr as one persistent process that serves filtered feeds and schedules
feed refreshes and library-rule evaluations. Replace the normal two-container
server/cron deployment with one container, while preserving standalone CLI use.
This is the daemon portion of project 3; the web UI and Helm chart follow later.

The user selected:
- A separate cron schedule for each outgoing list and each library rule.
- Cron notation for this version. The future UI must offer friendly controls and
  retain an advanced cron option; there is no UI implementation in this project.
- Direct calls to the existing Python core, with an HTTP server and one background
  worker, rather than spawning CLI subprocesses for every task.

The defaults and edge-case decisions below were implementation proposals and
were accepted with the user's approval of this document.

## Approaches

**Selected: in-process worker and core calls.** Reuse `engine.run`, list refresh,
report projections and the HTTP snapshot server. Keep the HTTP listener independent
of worker execution. One worker serializes scheduled work and avoids introducing
parallel destructive rule evaluation.

**Alternative: CLI subprocesses.** Existing commands provide an execution boundary
and isolate tasks, but introduce child-process shutdown, output parsing and status
translation. The user chose core calls to avoid those layers and prepare for the UI.

The scheduler calculates due times; it does not implement a second rule engine or
make HTTP requests through a newly added application API.

## Configuration and CLI

Add optional `schedule: "<cron expression>"` to `Rule` and `ProxyList`, default None.
No schedule means manual-only. A disabled library rule never becomes a scheduled
job, even with a schedule. Existing `run`, `preview`, `lists refresh`, `lists
preview`, `lists status` and `serve` commands retain their meanings; a schedule
never restricts explicit manual execution.

Add optional `scheduler` configuration with `timezone`, default `UTC`, validated
as an IANA zone. Use `Europe/Amsterdam` in the example. Do not infer the timezone
from locale, the host or Docker's TZ variable.

```yaml
scheduler:
  timezone: Europe/Amsterdam

rules:
  - name: Streaming movies
    target: radarr
    schedule: "0 2 * * *"
    preview: true
    action: delete_files
    when:
      streaming: my_providers

list_proxy:
  # Existing api_key, sources and optional tmdb_token remain here.
  lists:
    movies:
      target: radarr
      sources: [trending_movies]
      schedule: "0 * * * *"
      when:
        streaming: my_providers
```

The fragment illustrates new fields, not a complete standalone config.

- `excludarr daemon [--host 127.0.0.1] [--port 8989]`: run scheduling and, when
  list_proxy is configured, the existing feed HTTP server. Docker explicitly
  binds to 0.0.0.0. A library-only daemon requires no list_proxy/API key and opens
  no HTTP listener. Reject a daemon with neither an HTTP server nor scheduled jobs.
- `excludarr schedule status [-o table|json|yaml]`: local scheduler/job information,
  with no integration requests. Show job kind/name, cron, timezone, next planned
  time, pending/running state and last outcome/time/error. Without a running daemon,
  show that fact; do not present a calculated future occurrence as active scheduling.
- Startup prints timezone, scheduled jobs, next planned times, feed URLs and the
  existing API-key placeholder instructions. No secret or secret-bearing URLs.

The process loads fixed configuration at startup. Config/environment edits require
restart. Hot reload and an HTTP administration API are outside this version.

## Cron semantics

Accept exactly five fields: minute, hour, day of month, month and day of week.
Support ordinary ranges, lists, steps and names for months/weekdays. Use standard
cron OR semantics when both day-of-month and day-of-week are restricted. Reject
seconds/year fields, macros such as @reboot and library-specific random/hash/last-
day extensions in this first public contract. Reject impossible schedules during
config validation rather than spinning or silently producing no next occurrence.

Use a maintained cron parser (`croniter`, version constrained after API validation
in the implementation plan) and Python ZoneInfo; do not write a cron parser. Include
`tzdata` so named timezones work in Alpine images and installations without system
IANA data. These are focused dependencies, not a full background-job framework.

Store execution timestamps in UTC. Render table times in the configured timezone
with an offset; JSON/YAML expose timezone and aware timestamps explicitly.

For DST, skip a scheduled local wall minute that does not exist. A repeated local
wall minute in the autumn transition executes once, at its first occurrence. Use
UTC ordering for execution/deadline comparisons and test these policies explicitly;
do not inherit an unexamined parser-library DST default. Clock jumps never replay
completed occurrences. No sub-minute scheduling.

## Startup, delays and failures

Validate configuration and schedules, acquire the daemon lock, initialize storage
and bind HTTP before starting work. A bind/config/database failure exits nonzero
without running rules. Start feed serving immediately; do not wait for slow upstreams.

At startup, queue one refresh for each scheduled outgoing list whose snapshot is
missing, expired or incompatible. A valid existing snapshot stays usable without
an immediate extra refresh. Unscheduled lists remain manual-only, including their
initial refresh. Library rules never run merely because the daemon started.

Offline occurrences are not replayed after a restart. Compute future cron times
from startup. During normal operation, another task may keep the worker busy:
coalesce overdue occurrences of each waiting job into one pending execution, not
one execution per missed minute. A pending job retains its earliest unhandled
due timestamp; later occurrences do not move it behind newer jobs. Occurrences
of a job while that job is actively
running are skipped; after completion schedule its next future occurrence.
Pending jobs do not disappear simply because another job is still running.

Order pending work by earliest due time. For identical due times, refresh lists
first in configured list order, then evaluate library rules in YAML file order.
There is at most one pending entry per job. No retry/backfill job is added on
failure: record the result, keep the daemon alive, and wait for the next normal
cron time. Existing integration HTTP retries and timeouts remain in effect.

Only library rules with the same pending due UTC minute form a batch. At dispatch,
take the earliest pending due minute, process any tied lists first, then run that
minute's rules in YAML order as one subset through the existing engine. Never pull
a rule with a later due minute ahead of an intervening list. For example, rule B
due at 10:00, a list at 10:01 and rule A at 10:02 run B → list → A even if A is
first in YAML. Rules A and B both due at 10:00 run A → B in one batch. This preserves
shared item inventory, removed-item tracking and preflight within each batch. Only due rules are selected, but the engine retains the
full configuration for orphan-queue cleanup and rule references. Do not achieve
selection by deleting unscheduled rules from a copied Config. Preserve single-rule
CLI filtering while adding the internal subset interface.

If a rule batch stops on an error, completed rules retain their recorded outcomes,
the active rule records failure, and not-yet-started rules stay pending once. If
preflight fails before any rule begins, mark that due batch failed and move to its
next cron times; do not busy-loop retries. Other lists/jobs can still execute.

## Library and list behavior

Scheduled library execution is noninteractive, equivalent to selecting the due
rules with `run --yes`: existing preview flags, enabled flags, conditions, grace
periods, rescue exceptions and side effects remain authoritative. Scheduling a
rule does not turn preview off or bypass unknown-data protection.

A grace deadline makes an entry eligible; execution still occurs on that rule's
next scheduled evaluation. No separate queue-drain job or unscheduled execution
is introduced. Explain this for infrequently scheduled rules.

Use the existing list pipeline without changing its defaults: unknown decisions
follow `on_unknown`, missing export IDs exclude only the affected title, and source
failures preserve the previous snapshot without renewing its age. Feed expiry
remains six hours. Surface a configuration warning if consecutive list occurrences
can exceed the six-hour snapshot lifetime; accept the user's schedule nonetheless.

Scheduling fields and scheduler timezone are not feed-content changes. Exclude
`schedule` from outgoing-list fingerprints, including its default None, so adding
this release or adjusting a timetable does not invalidate otherwise compatible
existing snapshots.

## Lifecycle and concurrency

One background worker handles jobs; HTTP remains responsive during slow fetches
and rule actions. Create a fresh execution Context/clients for each feed job or
library batch, use per-operation database sessions, and close all HTTP clients
when the execution finishes or fails. Do not share SQLAlchemy sessions across
threads or reuse a failed integration circuit breaker forever across jobs.

Use a cross-process daemon singleton lock tied to the configured local SQLite
file, released by the OS on process exit. A second daemon using that database
fails clearly. This first daemon supports file-backed SQLite, rejecting memory
and non-SQLite database URLs for daemon mode; existing CLI database behavior is
unchanged.

Use a second execution lock associated with that same database for scheduled
execution and manual CLI `run`/`lists refresh`. A manual command fails clearly
when work is already active, rather than overlapping mutations. If manual work
owns the lock, the worker retains due work as pending and checks again without
busy-waiting. Apply locks around shared execution services, not separately nested
locks at both CLI and core entry points. Keep preview/read commands available.
Locking across multiple machines or different databases pointing to the same arr
is outside scope; document one daemon replica per deployment.

SIGINT/SIGTERM stops dispatching new jobs. Leave the HTTP server available while
the active execution finishes, then close resources/listeners and release locks.
Check a shutdown event between library rules so a pending rule batch does not
start further rules after a stop request. Do not terminate an in-flight destructive
request in application code. Docker's stop grace period is configurable and the
example must allow enough time; an external forced kill cannot guarantee completion.

## Status and persistence

Persist a small daemon heartbeat/instance record and per-job execution records in
SQLite through Alembic migrations. Job identity is `(kind, name)` so a rule and a
list may share a name. Each execution records scheduled/start/finish UTC times,
outcome, sanitized error and summary counts. Reuse existing library action history
and list snapshots for item details instead of duplicating them in job records.

Use outcomes success, warning, failed and interrupted. Unknown titles excluded by
policy and action side-effect warnings are warnings, not daemon crashes. Record
individual action failures as failed job outcomes even when the engine returns
normally. A completed preview-only rule is a successful evaluation, not an applied
action. An unexpected per-job exception records a sanitized failure and does not
stop future dispatch; programming errors remain diagnosable without logging config
objects, tokens or credential-bearing HTTP URLs.

Persist pending/running/next-due status for the active daemon. Write heartbeat
updates independently of the worker so a long operation does not look like a dead
process. A stale heartbeat means status unknown/offline, not proof no work is
running; the OS singleton lock is authoritative for starting a new daemon. On
restart under that lock, mark old unfinished executions interrupted and reconcile
job records with current configuration. Do not claim or retry uncertain external
actions automatically after a crash. Removed/renamed jobs are not dispatched.

## Deployment and delivery boundaries

Add daemon scheduling and execution services, minimal config fields, job storage,
CLI startup/status, shared mutation locking and focused dependency declarations.
Make only the engine-selection/lifecycle hooks necessary to reuse existing logic.

Keep `serve` read-only and schedule-free, existing cron mode working, and all
manual CLI commands available. The one-container Docker example uses command
`daemon --host 0.0.0.0`, CRON_MODE=false, the existing config/database volume and
an explicit stop grace period. Do not silently switch existing deployments or
run legacy cron and built-in scheduling together. Explain migration from the
two-container setup, disabling the old refresh container/cronjobs first.

Provide an English daemon guide, examples with schedules on actual list/rule
entries and updated README links. No UI routes, job editing endpoint, friendly
schedule form, Helm chart, notifications or distributed worker machinery now.
The future UI may translate friendly schedules to the same cron field and read
the persisted execution data without replacing these execution semantics.

## Verification

Use fake clocks and fake integrations, with no real sleeps or destructive live
requests. Cover five-field validation, timezone/DST transitions, file-order rule
subsets, disabled/manual-only jobs, no destructive startup/backfill, initial stale
feed refresh, bounded pending/coalescing, unchanged snapshot fingerprints,
independent task failure, preview/grace/rescue invariants, action-result failure
classification, CLI/daemon locking, singleton/crash recovery, client cleanup and
HTTP responsiveness during a blocked job. Test shutdown between rules and during
an active job. Check upgraded SQLite preserves existing queue/history/cache/feed
snapshots. Run the full existing suite, Ruff, example validation and container
startup/SIGTERM smoke checks before claiming implementation complete.

## References and decisions left to the builder

- Cron parser API: https://github.com/pallets-eco/croniter
- ZoneInfo and tzdata: https://docs.python.org/3/library/zoneinfo.html

The implementation plan chooses the exact parser version and cross-platform OS
file-lock implementation/dependency, a bounded poll/heartbeat cadence, concrete
job table/API names and shutdown hooks. These choices must satisfy the policies
above; do not add a general-purpose task framework or custom cron parser.

## Builder check

Independent read-only review found one ambiguity: grouping pending library rules
could conflict with oldest-due dispatch. Resolved as a builder decision: batch only
rules sharing a pending due UTC minute; preserve YAML order within that batch,
and chronological order between batches/lists. No other material unanswered
questions were identified. The user approved this resolved design before implementation planning.
