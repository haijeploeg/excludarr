# Daemon: one process for scheduling and feeds

`excludarr daemon` runs the feed server and scheduled work in one process.
Each outgoing list and library rule can have its own five-field cron schedule.
Standalone commands and the original `serve`/cron deployment remain available.
The daemon calls the same Python core as the CLI; it never spawns CLI subprocesses.

## Configure schedules

Start with [the complete daemon example](../.examples/daemon-example.yml), or add
these fields to your existing configuration:

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
```

Set `schedule` on each outgoing list under `list_proxy.lists` too:

```yaml
# Fragment inside list_proxy; keep your api_key, sources and other list fields.
lists:
  movies:
    target: radarr
    sources: [trending_movies]
    schedule: "0 * * * *"
    when:
      streaming: my_providers
```

These fragments are not complete configurations. The complete example requires
`RADARR_API_KEY`, `SONARR_API_KEY`, `LIST_PROXY_API_KEY` and `TMDB_READ_TOKEN`.
See [the proxy guide](list-proxy.md#1-configure-two-feeds) for generating the feed
key and obtaining the separate TMDB token. Excludarr does not automatically load
`.env` in a local shell; export variables, or use Compose's `env_file`.

| Schedule | Meaning in scheduler.timezone |
| --- | --- |
| `0 * * * *` | Every hour |
| `0 */2 * * *` | Every two hours |
| `0 2 * * *` | Daily at 02:00 |
| `0 3 * * SUN` | Sunday at 03:00 |
| `*/15 * * * *` | Every fifteen minutes |

The five fields are minute, hour, day of month, month and day of week. Ordinary
ranges, lists, steps and month/weekday names are supported. When both day fields
are restricted, either may match. Seconds/year fields, @reboot and extended
last-day/random/hash syntax are rejected. Impossible schedules fail validation.

The timezone defaults to **UTC**. It is not inferred from `profile.locale`, the
host or `TZ`. During daylight saving transitions, nonexistent local times are
skipped and a repeated local minute runs only at its first occurrence. Use a time
outside the transition hour if a daily run should not be skipped that day.

An omitted/null schedule means **manual-only**. A rule with `enabled: false` is
never scheduled. Adding a schedule does not turn off `preview`: preview rules
still report matches without applying actions. Once reviewed, set `preview: false`
if you want the scheduled rule to act. Rules keep their existing grace periods,
rescue exceptions, unknown-data protection and action side effects.

## Run locally

```bash
excludarr --config /path/to/excludarr.yml daemon
```

Keep this process running. Startup shows the timezone, configured jobs, next
planned times, and feed URLs with an API-key placeholder. For a remote arr or
container, choose a reachable bind address and free port:

```bash
excludarr --config /path/to/excludarr.yml daemon --host 0.0.0.0 --port 8990
```

The default HTTP bind is `127.0.0.1:8989`. Sonarr may already occupy that port.
Use the Excludarr host's address in Radarr/Sonarr, not `0.0.0.0` or the arr
container's own `localhost`. Feed paths and authentication are unchanged:

```text
http://YOUR_EXCLUDARR_HOST:8990/lists/movies?apikey=YOUR_FEED_KEY
http://YOUR_EXCLUDARR_HOST:8990/lists/series?apikey=YOUR_FEED_KEY
```

A library-only configuration needs no `list_proxy` section/API key and opens no
HTTP listener. A daemon with neither scheduled jobs nor configured feeds is rejected.
`serve` remains a feed-only command and does not start the scheduler.

## Startup, ordering and downtime

Scheduled feeds with missing, expired or incompatible snapshots refresh on startup.
Valid snapshots remain usable without an extra warm-up refresh. Unscheduled feeds
need a manual initial refresh and subsequent manual/external refreshes.

Library rules wait for their next cron occurrence; restarting the daemon never
triggers library cleanup merely because a run was missed while offline. There is
no replay of offline occurrences.

One worker performs tasks serially, leaving HTTP and heartbeat handling independent.
If another task keeps it busy, each waiting job retains one pending occurrence,
not a growing backlog. Occurrences while a job is actively running are skipped;
its next time is calculated after completion. Pending work keeps the oldest due
timestamp so frequent jobs cannot continually push an older job behind them.

The earliest due time wins. At a tied time, lists refresh first in configuration
order, then library rules run in YAML order as one engine pass. Rules with different
due times do not leap over intervening list work to form a larger batch.

A grace deadline makes an entry eligible; it executes only at that rule's next
scheduled evaluation. A weekly rule can therefore act later than the exact grace
deadline. Removing a schedule makes the rule manual-only, including queue handling.

A failed job does not crash the daemon or trigger an immediate retry loop; the next
normal cron occurrence tries again. Existing integration retries still apply.
List snapshots still expire after six hours. Startup/config validation warns when
the next two list occurrences are at least six hours apart. That check is advisory,
not a guarantee over every later calendar gap. A slow library task can also delay
feed work; choose schedules and monitor status accordingly.

Missing export IDs exclude only the affected title. List filtering and `on_unknown`
keep their existing semantics. Changing only a schedule/timezone does not invalidate
an otherwise compatible feed snapshot.

## Check status and run manual commands

```bash
excludarr schedule status
excludarr schedule status -o json
excludarr schedule status -o yaml
```

Status reads local SQLite data without integration requests. It shows the daemon's
heartbeat, each job's cron/timezone, pending/running state, next time and last result.
Table times use the configured timezone with an offset; structured timestamps are
aware and retain their timezone information.

- **success:** completed, including a successful preview-only evaluation.
- **warning:** completed with incomplete data or failed side effects; inspect the error/counts.
- **failed:** a source/engine/action failed; inspect the job error and existing item history.
- **interrupted:** a previous daemon stopped before confirming completion; external actions
  may already have happened. A restart does not automatically replay that occurrence.

A heartbeat older than fifteen seconds is marked stale; it is not permission to
start a second daemon. The native OS lock determines ownership, not heartbeat age.
Changing schedules/config while running requires a daemon restart; status flags
schedule/timezone mismatches as restart_required. There is no hot reload yet.

`run` and `lists refresh` share the execution lock with the worker. They fail clearly
if work is already active; retry after it finishes. Preview/read commands remain
available. Use the same config/database when inspecting or executing manual work.
Do not rely on locks between different databases targeting the same arr.

## Docker and migration from cron

Copy [daemon-compose.yml](../.examples/daemon-compose.yml) to `compose.yml` and
[daemon-example.yml](../.examples/daemon-example.yml) to `config/excludarr.yml`.
Put credentials in `.env` as described in the proxy guide. Use an image containing
these commands; for this checkout, build `docker build -t excludarr:dev .` and set
the Compose image to `excludarr:dev`.

To migrate the existing deployment:

1. Stop the old server/refresh containers and disable old library cronjobs.
2. Preserve `/config`, its YAML and SQLite database. Add schedules to the entries
   you actually want automated; unscheduled entries remain manual-only.
3. Use the daemon Compose command with `CRON_MODE: "false"` and the same volume.
4. Start it and check status and authenticated feed URLs:

```bash
docker compose up -d
docker compose exec excludarr excludarr schedule status
docker compose logs -f excludarr
```

The daemon requires a **local file-backed SQLite database** and **one replica**.
Memory/URI/non-SQLite databases are rejected in daemon mode; standalone CLI database
behavior remains unchanged. The adjacent `.daemon.lock` and `.execution.lock` files
must be writable. Keep them in place: process ownership is released by the OS even
if those files remain after exit. Shared/network filesystems and multi-host workers
are outside this deployment model.

The sample maps `8989:8989`; use `8990:8989` if the host port is occupied. Arrs on
the same Docker network can use `http://excludarr:8989/lists/movies?apikey=YOUR_FEED_KEY`.
For unrelated networks, use a reachable host address or explicitly share a network.

SIGINT/SIGTERM stops new dispatch and lets the active execution finish before
closing HTTP and releasing locks. Between rules, the remaining batch is not started.
The example sets `stop_grace_period: 5m`; raise it if one rule/refresh may take longer.
An external forced kill can interrupt requests and cannot guarantee their outcome.
On restart, unfinished job records become interrupted instead of silently successful.

After config edits, restart the daemon. After `.env` edits, recreate the container
with `docker compose up -d --force-recreate`; restart alone does not reload its
environment. Friendly scheduling controls and an advanced cron editor belong to
the later web UI; no UI or Helm chart is included here.
