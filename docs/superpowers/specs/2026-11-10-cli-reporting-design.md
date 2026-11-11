# Excludarr CLI reporting

Status: approved

## User goals

Excludarr should make the same decision easy to verify in a preview, before confirmation, and later in the queue or history. The user needs to know why a title matched, what will happen, when it will happen, and how much disk space the action is estimated to free. The terminal should have a recognizable visual style across commands and remain easy to scan with large libraries. All CLI copy is in English.

## Layout choices

The mockups explored one compact overview (A) and separate blocks per rule (B). The user leaned toward A because it keeps rows easy to scan. Separate action and evidence lines under table rows in the first queue and history mockups were difficult to follow.

- **Preview and run use A as the starting point.** Lead with the command, scope and totals. Keep a rule overview and a compact table of matched titles. Each title must be attributable to the rule and planned action without requiring the reader to infer the association from the match evidence.
- **Queue uses Q1.** One table ordered by due time by default. Put due time, title, size, rule, planned action and original match evidence on the same row. Keep supported sort options.
- **History uses H1.** One chronological table, newest actions first. The full action timestamp is the first column. Put title, item size, reported space freed, action, match evidence, result and any failure or cleanup warning on the same row.
- **Cache status uses A as the starting point.** A compact table summarizes cache data by type.

Use a shared Excludarr heading and consistent accents for actions, successes, waiting and failures. Every status has a readable text label. Long titles and evidence wrap within their rows on narrower terminals. Short commands such as `providers list`, `config validate`, `rescue` and `exceptions` use the same heading, status vocabulary and table style where they return multiple rows.

## Match evidence and detail levels

The default table shows the observed values that made the rule match. Render evidence from the evaluation that made the decision. Examples include the configured provider and matching offer type, or the requester's last qualifying play and the threshold used. For `all`, report the satisfied clauses. For `any`, report a decisive satisfied branch. For `not`, report the known result of the inner clause. The existing three-valued evaluation and `unless` behavior continue to govern execution.

`--show-all` on `preview` and `run` adds available context for matched titles. This includes configured streaming providers, viewers, Seerr requests, labels and the age of the local file when supported by the source data. Hide data from unconfigured integrations. Watch history requires Plex and Tautulli. Show Seerr request status and requester names without inferring the import route from a missing request. Use file dates for file age and keep library-entry dates distinct. Missing historical fields remain unavailable.

`--debug` exposes decision diagnostics, including unresolved conditions and their causes, integration failures and retries, JustWatch IDs and candidates, and cache freshness. These details are separate from `--show-all`. The standard rule overview shows match counts without unresolved counts.

## Preview, confirmation and outcomes

`preview` simulates configured actions, including actions on rules marked `preview: true`. Its English banner explains that the command performs no actions, identifies protected rules and points to `run`. The simulation shows the concrete action and side effects, whether a title would execute, queue, wait or be skipped, and deduplicated estimated space freed on execution and after grace. Keep matched size distinct from estimated space freed.

Before confirmation, `run` shows the titles, match evidence and effects for the action being confirmed. Preserve rule selection, queue timing, interactive skips, protection via `preview: true` and the existing confirmation controls. After execution, distinguish success, main action failure and success with cleanup warnings. Report measured or reported bytes from the action separately from pre-execution estimates. Titles declined or skipped at confirmation are distinguishable from attempted actions.

Capture match evidence when an item is queued and capture the evidence used when an action is attempted. Queue evidence describes the earlier decision and is not re-evaluated by the `queue` command. The planned action comes from the current rule, since execution re-evaluates that rule when the item is due. Mark rows whose rules are disabled or missing. Save action-time item size and structured outcome details for new history records. Keep prior queue and history rows readable through additive storage changes. Display missing evidence, size or warning details for prior rows as unavailable without inventing historical values.

## Output formats

Table output is the default, including under cron. `-o` or `--output` accepts `table`, `json` and `yaml` on `preview`, `run`, `queue`, `history`, `cache status`, `rescue`, `exceptions list`, `exceptions remove`, `providers list` and `config validate`. Use the same report data for table rendering and serialization. JSON and YAML contain all available report fields relevant to the command independently of `--show-all`. Include match evidence, available integration context, planned and actual outcomes, warnings and relevant identifiers where applicable. Use byte counts and unambiguous UTC timestamps. Output one report document per command, including when the user declines confirmation. CLI parsing errors and help continue to use the CLI's own output. Exclude credentials and raw integration payloads from reports.

Structured output preserves normal confirmation. Write the human-readable confirmation prompt, selection interaction, progress and diagnostic logs to stderr. Reserve stdout for the JSON or YAML document. Existing unattended confirmation options continue to work. If a command reports a cancellation or a handled configuration, integration or action error after parsing, its document includes that outcome and any results already recorded. Preserve the current exit status meaning for errors and action failures.

## Cache and progress

`cache status` reads the stored metadata without fetching source data. Show age since fetch and the next expiry separately for JustWatch providers, title matches and offers. Summaries report the oldest entry and earliest expiry in each group. Mark expired entries as due for refresh when next used. Store fetch timestamps for newly written entries. Older entries with only expiry metadata show an unavailable age until refreshed. With `--debug`, identify the entries used by the command and their fetch and expiry times.

`preview --refresh` and `run --refresh` fetch the cache-backed data used by the selected command and update entries on successful lookup. Reuse the result of a successful fetch within the command. If refreshing a source fails, a stale value cannot establish a match in that command. A rule still matches when its result is independently established, such as an `any` branch that is known true. An unresolved result cannot trigger an action. Other rules can continue when their required facts are available.

`--progress` remains opt-in. Show the current phase or waiting integration, elapsed time and completed/total when a total is known. During an API wait, continue updating elapsed time. Retry details are debug diagnostics. Pause the live display for prompts and visually separate it from the final report.

## Scope and acceptance

The work covers CLI reporting and the supporting evaluation evidence, cache metadata and historical snapshots. It retains the existing rule language, action behavior and integration clients. The list proxy and web UI are separate projects.

- The same title can be traced from match evidence in preview, to the confirmation, to its queue snapshot or history outcome.
- Queue and history match the selected Q1 and H1 layouts, including one row per queue entry or action and a leading due time or execution time.
- Table, JSON and YAML agree on match counts, dates, outcomes and byte estimates. Structured stdout remains parseable with confirmation, progress or debugging active.
- A failed forced refresh cannot authorize a removal using stale data. Independent decisive branches still work.
- Prior databases remain readable and new evidence appears on newly written records.

The builder may choose the exact Rich primitives, color shades, column widths, schema field names and internal report types. The required behaviors and the chosen layouts define the review criteria.
