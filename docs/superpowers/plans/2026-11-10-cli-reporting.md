# Excludarr CLI Reporting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Excludarr reports consistent, show verifiable match evidence, and expose the same results as tables, JSON or YAML.

**Architecture:** Capture observed values during rule evaluation and store the evidence with queue and history events. Project command results into explicit, safe report records that feed the terminal and structured renderers. Keep freshness and progress at the source boundaries so display choices cannot affect the rule decision.

**Tech Stack:** Python ≥ 3.12, Typer, Rich, PyYAML, httpx, SQLAlchemy, Alembic, pytest, respx, Ruff.

**Spec:** [Excludarr CLI reporting design](../specs/2026-11-10-cli-reporting-design.md).

## Global Constraints

- All CLI copy is in English. A is the starting point for preview, run and cache. Queue uses Q1 and history uses H1.
- Table output is the default, including under cron. JSON and YAML use byte counts and unambiguous UTC timestamps.
- Preserve existing three-valued rule logic, action behavior, exit meanings, preview protection, selectors and confirmation controls.
- Keep credentials, raw integration payloads and HTTP debug headers out of reports. Treat title, rule and integration text as literal terminal text.
- Keep prior databases readable. Store missing historical values as unavailable.
- Work from the current tree, which already contains uncommitted preview and diagnostic changes. Include those in any isolated execution baseline. Do not commit without the user's instruction.
- Use the existing dependencies and no-network tests. Run commands with `.venv/bin/`.

## Review Focus

1. A forced refresh times out with an unexpired cached match. The old value cannot authorize deletion, and an independent true `any` branch can still match. Task 4.
2. JSON or YAML execution receives a negative answer, EOF, or a failure after earlier actions. Stdout is a single parseable report and earlier outcomes remain visible. Task 5.
3. An old database contains queue and history records and cache entries. Upgrading preserves timestamps, due dates, results and expiry, with unknown fetch dates and evidence. Tasks 2 and 4.
4. A rule changes action or becomes disabled after queuing. Queue retains the old evidence and describes the current plan without suggesting a disabled action will run. Task 2.
5. Two matched rules target the same file and an action keeps files. The confirmation and preview show distinct file size and reclaimed bytes without double counting. Task 3.

## File responsibilities

- `conditions.py`, `engine.py`, `facts.py` and `items.py` capture observed evidence, execution outcomes and optional item details.
- `storage/models.py`, `storage/repo.py` and additive Alembic revisions persist event snapshots and cache timestamps.
- New `reporting.py` defines safe command projections and JSON/YAML serialization. `output.py` renders these projections with Rich. `cli.py` selects formats and owns interaction and output streams.
- `preview.py` remains the source of planned actions and deduplicated savings. `clients/http.py` supplies API wait and retry signals without changing request policy.

### Task 1: Capture evidence from the evaluation

**Files:** Modify `src/excludarr/conditions.py`, `src/excludarr/engine.py`, `src/excludarr/facts.py`. Test `tests/test_conditions.py`, `tests/test_engine.py`.

**Interfaces:** Add `Evidence(condition: str, result: bool, observed: dict[str, Any])` in `conditions.py`. The observed mapping contains JSON-safe scalars, lists and maps. Extend `evaluate(cond, item, ctx, *, unknown_reasons=None, evidence: list[Evidence] | None = None) -> bool | None`. Add `Match.evidence: list[Evidence]` with an empty default.

- [ ] Add `test_any_evidence_uses_decisive_branch`, `test_not_evidence_proves_false_inner_clause` and `test_requester_evidence_has_play_and_threshold` with the existing condition fakes.

  ```python
  assert result is True
  assert [entry.condition for entry in evidence] == ["streaming"]
  assert evidence[0].observed["matched_offers"] == [{"provider_id": 8, "type": "FLATRATE"}]
  # For not, retain the known false result of its child.
  assert not_evidence[0].result is False
  # For requester_watched_more_than, retain the actual play time and threshold.
  assert requester_evidence[0].observed["last_played_at"] == played_at.isoformat()
  assert requester_evidence[0].observed["threshold_seconds"] == 30 * 86400
  ```

- [ ] Run `.venv/bin/pytest -q tests/test_conditions.py -k evidence`. Expect failure because `evaluate` cannot collect evidence.
- [ ] Extend leaf evaluation to return the observed values alongside its current result, then collect proof inside `evaluate`. Cover the leaf registry, including item fields, comparisons, age, request, watch and availability. Capture inputs at the point of decision without a second integration lookup. Availability evidence includes only qualifying offers and their covered units. Resolve provider IDs to display names using the catalogue already used for evaluation.
- [ ] Combine child proofs in rule order. Prove true `all` with all children and true `any` with the first true child. Apply the dual rules for known false results needed by `not`. Preserve unknown causes separately. In `evaluate_rule`, keep the existing top-level condition counts and attach proof only to confirmed matches.
- [ ] Run `.venv/bin/pytest -q tests/test_conditions.py tests/test_engine.py`. Expect the new evidence tests and all existing truth tables, skip and `unless` tests to pass.

### Task 2: Persist evidence and render Q1 and H1

**Files:** Modify `src/excludarr/storage/models.py`, `src/excludarr/storage/repo.py`, `src/excludarr/engine.py`, `src/excludarr/cli.py`, `src/excludarr/output.py`. Create the next Alembic revision after `0001_initial.py` in `src/excludarr/storage/migrations/versions/`. Test `tests/test_repo.py`, `tests/test_engine.py`, `tests/test_cli_commands.py`.

**Interfaces:** Extend `QueueEntry` with nullable `evidence`, and `HistoryEntry` with nullable `evidence`, `size_bytes` and `side_effect_errors`. Keep existing `Repo.queue_add` and `Repo.history_add` positional arguments and add these fields as optional keyword arguments. Persist evidence as JSON maps with the fields from Task 1. Extend `print_queue(rows, console=None, *, rules)` to receive current rules keyed by name.

- [ ] Add `test_reporting_migration_preserves_legacy_rows`, `test_due_action_records_current_evidence` and `test_queue_reports_current_action_with_original_evidence`. Build the legacy database at revision `0001` and insert rows before opening it with `Repo`.

  ```python
  assert old_queue.due_at == original_due_at
  assert old_queue.evidence is None
  assert old_history.size_freed == 4096 and old_history.size_bytes is None
  assert old_history.evidence is None and old_history.side_effect_errors is None
  assert new_history.evidence == execution_evidence
  assert new_history.side_effect_errors == ["seerr: timeout"]
  assert new_history.ok and new_history.size_bytes > new_history.size_freed
  assert "Disable monitoring" in queue_stdout and "Netflix" in queue_stdout
  assert "Rule disabled" in disabled_queue_stdout
  ```

- [ ] Run `.venv/bin/pytest -q tests/test_repo.py tests/test_engine.py tests/test_cli_commands.py -k 'reporting_migration or due_action_records or queue_reports_current'`. Expect failure due to missing columns, snapshots or queue labels.
- [ ] Add nullable columns and map them in `Repo`. Record `Match.evidence` at enqueue, and re-evaluated evidence, item size and the structured side-effect errors when an action is attempted. Keep the stored execution timestamp and action code. Use a nullable warning field for legacy rows whose combined detail cannot be parsed reliably.
- [ ] Render Q1 as one row per queue entry, ordered by due time by default. Show the current rule's action, with `Rule disabled` or `Rule missing` when appropriate. Render H1 newest first with a full UTC timestamp first and all action data on the same row. Show legacy unavailable fields with a dash. Use literal Rich text and let long cells wrap inside the row.
- [ ] Run `.venv/bin/pytest -q tests/test_repo.py tests/test_engine.py tests/test_cli_commands.py`. Expect migration and rendering tests to pass alongside existing queue, rescue and history tests.

### Task 3: Share preview, confirmation and run report data

**Files:** Create `src/excludarr/reporting.py`. Modify `src/excludarr/cli.py`, `src/excludarr/output.py`, `src/excludarr/engine.py`, `src/excludarr/items.py`, `src/excludarr/preview.py`. Test `tests/test_cli_commands.py`, `tests/test_preview.py`, `tests/test_items.py`.

**Interfaces:** Define `run_document(reports: list[RuleReport], *, dry_run: bool) -> dict[str, Any]` with `command`, `status`, `summary`, `rules` and `errors`. Rule rows contain name, level, concrete action, related changes, and match rows. Match rows contain item key, title, size in bytes, evidence, context, planned step, due time and outcome. Add `RuleReport.skipped` and `RuleReport.declined` sets of item keys. Add optional `MediaItem.file_added_at: datetime | None` while retaining `added` for rule logic.

- [ ] Add `test_confirm_shows_effects_evidence_and_reclaimable_bytes` and `test_table_show_all_adds_configured_context_only`. Use two matching rules for the same movie and a monitor action on a separate file.

  ```python
  assert report["summary"]["estimated_now_bytes"] == first_movie_bytes
  assert "0.00 GB estimated space freed" in monitor_confirmation
  assert "Netflix" in confirmation and "Delete files" in confirmation
  assert match["outcome"]["status"] == "declined"
  assert "Requested by" not in stdout_without_seerr
  assert "Watched by" not in stdout_without_plex_and_tautulli
  assert "Label: family" in show_all_stdout
  ```

- [ ] Run `.venv/bin/pytest -q tests/test_cli_commands.py -k 'effects_evidence or configured_context'`. Expect failure because confirmation uses total matched size and the table includes unrelated integration columns.
- [ ] Build the explicit projections from engine reports and `preview.estimated_savings`. Reuse `preview.reclaimable_files` for the confirmation batch. Record interactive skips and declined batches without altering action selection or queue writes. Keep intended steps distinct from executed results.
- [ ] Render A with one command summary, a rule overview, and a title table that associates every title with its rule and planned action. Use the same evidence and concrete effects for the prompt. Apply the shared heading and status styles from Q1 and H1.
- [ ] Add `--show-all` to run and preview. Fetch extra provider, viewer and requester details only when the requested report needs them. Use labels and available file dates from the existing integration payloads. Derive Sonarr dates from file records, and Radarr dates from movie-file data when supplied. Never substitute a library date for a missing file date. Keep compact output free of optional lookups and columns.
- [ ] Run `.venv/bin/pytest -q tests/test_cli_commands.py tests/test_preview.py tests/test_items.py`. Expect preview and confirmation to agree on evidence and estimates, and actual actions to retain their current results.

### Task 4: Add cache status and scoped refresh

**Files:** Modify `src/excludarr/storage/models.py`, `src/excludarr/storage/repo.py`, `src/excludarr/facts.py`, `src/excludarr/engine.py`, `src/excludarr/conditions.py`, `src/excludarr/cli.py`, `src/excludarr/output.py`. Create the Alembic revision after Task 2. Test `tests/test_repo.py`, `tests/test_facts_streaming.py`, `tests/test_engine.py`, `tests/test_cli_commands.py`.

**Interfaces:** Add `CacheEntry(value: Any, fetched_at: datetime | None, expires_at: datetime)`, `Repo.cache_entry(key: str) -> CacheEntry | None` and `Repo.cache_metadata() -> list[tuple[str, datetime | None, datetime]]`. Preserve `cache_get` and `cache_set` call signatures. Add `Context(..., *, refresh: bool = False)`. Add the cache status command and `--refresh` to preview and run.

- [ ] Add `test_legacy_cache_preserves_expiry_with_unknown_fetch_time`, `test_cache_status_reads_only_metadata`, `test_forced_refresh_reuses_success_within_run`, `test_failed_forced_refresh_does_not_authorize_stale_removal` and `test_failed_refresh_does_not_block_decisive_any_branch`. Include a provider catalogue timeout and a cached negative title match in the fixtures.

  ```python
  assert legacy.fetched_at is None and legacy.expires_at == original_expiry
  assert fresh.fetched_at == frozen_now and fresh.expires_at == frozen_now + ttl
  assert status_result.exit_code == 0 and not respx.calls
  assert fresh_search_calls == 1 and fresh_offers_calls == 1
  assert failed_refresh_report.matches == [] and executed == []
  assert original_cache_entry == repo.cache_entry(key_after_failure)
  assert independent_report.matches[0].evidence[0].condition == "monitored"
  ```

- [ ] Run `.venv/bin/pytest -q tests/test_repo.py tests/test_facts_streaming.py tests/test_engine.py tests/test_cli_commands.py -k 'legacy_cache or cache_status or forced_refresh or failed_refresh'`. Expect failure because timestamps, the status command and forced refresh are absent.
- [ ] Store fetch time and expiry together on successful cache writes. Keep nullable fetch times for legacy rows. Inspect metadata without reading payloads or contacting integrations. Group by provider catalogue, title match and offer key, including legacy keys. Render oldest known age and earliest expiry, with an explicit next-use refresh state for expired entries.
- [ ] Centralize JustWatch cache access in `Context` for provider catalogue, ID matches and offers. On a forced refresh, bypass persistent values, including legacy positives. Reuse a successful result per cache key within the command, including across prefetch workers. Failed lookups preserve old cache entries for later invocations and provide unknown results for this one. Log cache source, fetch and expiry times in debug. Keep matching fallback and country-specific offers.
- [ ] Treat transient refresh failure of a provider catalogue as an unavailable streaming fact. Preserve configuration validation errors and the existing library-loading preflight. Keep independently proven rules and `any` branches eligible. Never fall back to stale data for the failed refresh.
- [ ] Run `.venv/bin/pytest -q tests/test_repo.py tests/test_facts_streaming.py tests/test_engine.py tests/test_cli_commands.py`. Expect all refresh safety cases, historical database tests and existing evaluation tests to pass.

### Task 5: Expose structured output and preserve confirmation

**Files:** Modify `src/excludarr/reporting.py`, `src/excludarr/cli.py`, `src/excludarr/output.py`, `src/excludarr/engine.py`. Test `tests/test_cli_commands.py`, `tests/test_cli.py`.

**Interfaces:** Add `OutputFormat` with `table`, `json`, `yaml`, and `serialize(document: dict[str, Any], format: OutputFormat) -> str`. Add `-o` / `--output` to every command listed in the spec. For non-run commands project the same row and outcome data consumed by their table presenter into `command`, `status`, `summary`, `items` and `errors`. Add optional `engine.run(..., on_report: Callable[[RuleReport], None] | None = None)` to make partial results available as each rule report is registered.

- [ ] Add `test_structured_preview_has_all_context_regardless_of_show_all`, `test_structured_run_confirmation_keeps_stdout_parseable` and `test_structured_run_reports_partial_results_on_abort`. Parametrize JSON and YAML. Exercise decline, EOF after an earlier successful rule, and a handled configuration error. Check one document for each other supported command, including empty lists.

  ```python
  assert parse(result.stdout) == parse(show_all_result.stdout)
  assert parsed["rules"][0]["matches"][0]["context"]["providers"] == ["Netflix"]
  assert "Execute" in result.stderr and "Execute" not in result.stdout
  assert declined["status"] == "declined" and executed == []
  assert aborted["status"] == "aborted" and successful_action in prior_outcomes
  assert failed["status"] == "error" and result.exit_code == 1
  assert api_key not in result.stdout and api_key not in result.stderr
  ```

- [ ] Run `.venv/bin/pytest -q tests/test_cli_commands.py -k structured`. Expect failure because the output option is absent.
- [ ] Implement serialization with `json.dumps` and `yaml.safe_dump` over explicit projections. Emit one document from the command boundary. Structured modes always request full report context. Wrap handled errors and aborts in the report and preserve any completed results, exit codes and existing prompt decisions. Keep prompts, interactive selection, debug and progress on stderr. Keep normal CLI parser behavior for syntax errors and help.
- [ ] Add format support to queue, history, cache status, rescue, exception list and remove, provider list, and config validation. Use the same source rows as their table renderers. Expose validation results and safe errors without serializing the underlying configuration.
- [ ] Run `.venv/bin/pytest -q tests/test_cli_commands.py tests/test_cli.py`. Expect structured stdout to parse in every supported mode, with confirmation and exit behavior intact.

### Task 6: Show API waits, verify terminal output and document usage

**Files:** Modify `src/excludarr/clients/http.py`, `src/excludarr/facts.py`, `src/excludarr/cli.py`, `src/excludarr/output.py`, `README.md`. Test `tests/clients/test_http.py`, `tests/test_cli_commands.py`.

**Interfaces:** Reuse the engine progress callback `(message: str, completed: int, total: int | None) -> None`. Add `HttpClient.on_wait: Callable[[str, bool], None] | None`, receiving the integration name and `True` on entry or `False` on exit. Keep retry policy in `HttpClient` and log retry decisions at debug level.

- [ ] Add `test_http_wait_progress_and_retry_diagnostics` and `test_structured_progress_keeps_report_stream_clean`. Use a fake clock and mocked retries so tests run without sleep or network.

  ```python
  assert wait_events == [("radarr", True), ("radarr", False)]
  assert "Retrying Radarr" in debug_messages and "Retrying Radarr" not in progress_output
  assert "Waiting for Radarr" in result.stderr
  assert parse(result.stdout)["command"] == "preview"
  ```

- [ ] Run `.venv/bin/pytest -q tests/clients/test_http.py tests/test_cli_commands.py -k 'wait_progress or structured_progress'`. Expect failure because waits and retries have no separate reporting.
- [ ] Connect wait notifications and current operation to opt-in Rich progress. Show elapsed time during a wait and known totals when processing items. Parallel JustWatch requests retain their shared completed count. Pause the display for prompts and finish it before the report, with a blank line in table mode. Keep individual retries in debug logs.
- [ ] Document table defaults, `-o json`, `-o yaml`, confirmation in structured mode, `--show-all`, `--debug`, `--progress`, `--refresh` and `cache status`. Describe cache expiry as a refresh on next use and distinguish estimated from reported space freed.
- [ ] Run `.venv/bin/pytest -q`, `.venv/bin/ruff check src tests`, `.venv/bin/ruff format --check src tests` and `git diff --check`. Expect all to pass. Smoke-test A, Q1 and H1 with synthetic titles and errors at 80 and 120 terminal columns. Inspect timestamps, wrapped evidence and the separation of progress from reports.
