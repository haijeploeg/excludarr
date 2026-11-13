# Minimum Streaming Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Let users require `sd`, `hd` or `4k` streaming quality in library rules and outgoing lists.

**Architecture:** Preserve quality on individual JustWatch offers and evaluate it alongside provider and monetization in the existing streaming leaf. All callers, including daemon jobs, use that shared implementation. Version offer-cache entries; retain existing unknown and snapshot compatibility policies.

**Tech Stack:** Existing Python >=3.12, Typer, Pydantic, httpx, SQLAlchemy, pytest/respx and Rich. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-13-streaming-quality-design.md`

## Global Constraints

- Accept exactly `sd`, `hd` and `4k`, ordered SD < HD < 4K.
- The default remains no quality restriction. No profile-level setting is added.
- Missing and unfamiliar values remain unknown, never guessed.
- Lists retain their configured `on_unknown` policy; do not change its default.
- Preserve existing selection of episodes and three-valued boolean semantics.
- No local quality comparisons, HDR/audio/720p/1080p settings or UI work.
- No new dependency, automatic commit, push or production-library mutation.
- Execute from a feature checkout based on current `main`, which includes the daemon and PR #117. Do not reset or overwrite the existing local daemon branch. Establish isolation using the worktree skill at execution time.
- Keep code/docs English and conversation Dutch. Leave commits to the user.

## Review Focus

- An SD subscription plus a 4K purchase must not satisfy a 4K subscription requirement: Task 2.
- Unknown quality must not become true through negation or destructive daemon execution: Tasks 2 and 3.
- Multiple qualities on one provider must not inflate episode coverage or fail sorting when mixed with unknown: Tasks 1 and 2.
- A warm pre-upgrade cache must refetch quality without poisoning unrelated match data: Task 1.
- Changing the minimum must invalidate an outgoing snapshot, while unknown inclusion remains explicit: Task 3.

## File map

- `src/excludarr/clients/justwatch.py`: offer shape and presentation normalization. Existing query already requests the field.
- `src/excludarr/facts.py`: cache serialization, versioned offer key, provider-context aggregation.
- `src/excludarr/conditions.py`: parse, evaluate and describe the streaming minimum.
- `src/excludarr/output.py`: render quality evidence; preserve structured report data through existing reporting code.
- `src/excludarr/lists/service.py`: existing fingerprint integration; only change if the parsed condition does not already capture the new setting.
- `README.md`, `docs/list-proxy.md`, `.examples/excludarr-example.yml`, `dev/excludarr.yml`, `dev/README.md`: user-facing configuration and manual scenario.
- Tests listed below cover the shared behavior; update existing offer/cache fixtures in `tests/test_cli.py`, `tests/test_cli_commands.py`, `tests/test_list_commands.py` and `tests/test_list_service.py` when their shape changes.

### Task 1: Preserve offer quality through the client and facts cache

**Files:** `src/excludarr/clients/justwatch.py`, `src/excludarr/facts.py`, `src/excludarr/conditions.py`; `tests/clients/test_justwatch.py`, `tests/test_facts_streaming.py` and existing offer fixtures.

**Interfaces:** Change `Avail` to `frozenset[tuple[int, str, str | None]]` representing provider ID, uppercase monetization and normalized quality. Keep the signatures of `movie_offers()`, `show_offers()` and `Context.streaming()` otherwise unchanged. Existing unrestricted streaming evaluation must keep working with the new shape.

- [x] Add `test_offers_preserve_quality_variants`: one provider's SD/HD/_4K offers survive as separate entries; expected normalized qualities are `sd`, `hd`, `4k`.
- [x] Add `test_missing_and_unrecognized_presentation_are_unknown`: missing, null and unfamiliar presentation values yield `None`, retaining provider/monetization. Cover movie and episode parsing.
- [x] Add `test_quality_cache_round_trip_and_legacy_refetch`: a warm `jw:offers:` entry is ignored, the next request populates `jw:offers:v2:`, and a fresh Context reads the new entry without HTTP. Preserve title-match cache keys and TTL.
- [x] Run those tests and confirm failures before implementation.
- [x] Normalize the three known JustWatch values in `_avail()` and preserve unknowns. Update all offer unpacking, serialization and fixtures together. Sort offer tuples with an explicit quality fallback so `None` and strings cannot raise a comparison error.
- [x] Add `test_quality_variants_do_not_inflate_provider_coverage`: a provider offering SD and HD on one of two episodes renders `1/2`, not `2/2`; mixed known/unknown entries serialize without error.
- [x] Run `.venv/bin/pytest -q tests/clients/test_justwatch.py tests/test_facts_streaming.py tests/test_conditions.py tests/test_cli.py tests/test_cli_commands.py tests/test_list_commands.py tests/test_list_service.py` and confirm the representation change preserves existing behavior.

### Task 2: Configure, evaluate and explain the minimum

**Files:** `src/excludarr/conditions.py`, `src/excludarr/output.py`; `tests/test_conditions.py`, `tests/test_config.py`, `tests/test_cli_commands.py`.

**Interfaces:** `_streaming(v)` returns `(providers, monetizations, minimum)` with `minimum: str | None`. `_streaming_eval(p, item, ctx)` retains its existing `Observation | None` interface. Evidence adds `min_quality` and a `quality` field on each matched offer. Unknown evaluation uses existing evidence/reason machinery.

- [x] Add `test_streaming_min_quality_validation`: accept `sd`, `hd`, `4k` and omission; reject `SD`, `_4K`, `1080p`, null, booleans, numbers and empty strings when explicitly supplied. The shorthand remains unrestricted.
- [x] Add `test_streaming_minimum_ordering`: SD/HD/4K offers against each threshold produce the 3-by-3 ordering table, and unrestricted conditions still accept unknown quality.
- [x] Add `test_quality_cannot_be_combined_across_offers`: SD FLATRATE + 4K BUY fails an HD FLATRATE condition; 4K on an unconfigured provider also fails. A qualifying HD FLATRATE offer makes it true.
- [x] Add `test_quality_unknown_truth_table`: below-minimum + eligible unknown is unknown; qualifying + unknown is true; unknown on an ineligible provider/type does not affect false. `not unknown` stays unknown. No offers and no units remain false.
- [x] Add `test_season_quality_requires_every_selected_episode`: known true + unknown gives unknown, true + false gives false, false + unknown gives false, and all true gives true. Allow coverage across configured providers.
- [x] Run `.venv/bin/pytest -q tests/test_conditions.py tests/test_config.py` and confirm the new tests fail before implementation.
- [x] Extend parsing and validation, then apply existing three-valued aggregation to per-unit quality results. Do not add a separate condition or a local-file dependency.
- [x] Add `test_quality_evidence_in_table_and_structured_preview`: a minimum-HD condition matching a 4K subscription shows both the threshold and observed quality; JSON/YAML retain provider/type/quality/coverage. Normalize ANSI before text assertions.
- [x] Extend `_streaming_label()` and `evidence_text()` to explain the requirement and qualifying qualities, without inventing quality for unknown offers.
- [x] Run `.venv/bin/pytest -q tests/test_conditions.py tests/test_config.py tests/test_cli_commands.py` and confirm all pass.

### Task 3: Verify lists, snapshots and daemon execution

**Files:** `tests/test_list_filtering.py`, `tests/test_list_config.py`, `tests/test_list_snapshots.py`, `tests/test_daemon.py`; shared production code only if a test reveals an integration gap.

**Interfaces:** Retain `decide()`, `fingerprint()` and `execute_batch()` signatures. Use the parsed streaming condition from Task 2; no duplicate filtering logic.

- [x] Add `test_list_quality_uses_exclusion_semantics`: with an HD exclusion condition, SD-only streaming keeps the item included and qualifying HD excludes it. Test both unknown policies and unknown quality in `unless`.
- [x] Add `test_quality_changes_snapshot_fingerprint`: omitted minimum, HD and 4K produce different fingerprints; a snapshot created for HD is invalid after changing to 4K. Confirm the current canonical parsed-condition serialization supplies this automatically before changing production code.
- [x] Add `test_daemon_quality_matches_and_unknowns`: execute a scheduled, preview-only movie rule against known HD, SD and unknown-quality fixtures. Only HD matches; unknown is recorded as a warning; queue/history stay empty and no action runs.
- [x] Run `.venv/bin/pytest -q tests/test_list_filtering.py tests/test_list_config.py tests/test_list_snapshots.py tests/test_daemon.py` and confirm behavior. For integration tests that already pass through the shared implementation, retain them as contract checks; do not manufacture production changes just to make them fail first.

### Task 4: Document and verify the complete user workflow

**Files:** `README.md`, `docs/list-proxy.md`, `.examples/excludarr-example.yml`, `dev/excludarr.yml`, `dev/README.md`; existing example-config tests.

**Interfaces:** Document `streaming.min_quality` with exactly the values and unknown behavior defined above. Add a preview-only `streaming-movies-hd` dev rule alongside the unrestricted example, using the same fixture protection. No extra configuration file or launcher option.

- [x] Document threshold ordering, unknown-quality behavior, list exclusion semantics and `on_unknown: include`. Explain catalog quality versus account/device capability and the one-time offer-cache refetch after upgrade.
- [x] Add the dev scenario and command `make dev ARGS="preview --rule streaming-movies-hd --details"`. Explain why unrestricted and HD previews may differ without hard-coding live catalog counts.
- [x] Validate examples with existing example/manual-config tests. Review all consumers found by `rg 'Avail|jw:offers|matched_offers|FLATRATE' src tests` for stale tuple shapes and cache keys.
- [x] Run `.venv/bin/ruff format --check src tests`, `.venv/bin/ruff check src tests`, `git diff --check` and `.venv/bin/pytest -q`. Repeat the relevant CLI checks with forced color. Record actual failures; do not call the suite green if any remain.
- [x] Perform read-only JustWatch movie and episode lookups, verifying normalized qualities and safe handling of missing quality. Do not change production media or use live catalog results as unit-test expectations.
- [x] Run the manual preview against the isolated dev stack and check quality evidence and zero mutation. Rebuild its image if source changes require it.
- [x] Complete one final independent review of the combined change using the execution skill's review gate, then report checks and limitations. Leave changes uncommitted and supply a Conventional Commit message only if requested.

## Plan self-review

The tasks cover configuration, same-offer matching, unknown aggregation, unchanged unit selection, cache invalidation, deduplicated context, output evidence, list fingerprint/policies, daemon execution and documentation. One shared offer representation feeds all callers. No new infrastructure, dependency, migration or user setting beyond `min_quality` is planned.


## Completed verification

- macOS/Python 3.14, `TERM=xterm-256color FORCE_COLOR=1 .venv/bin/pytest -q`: 544 passed.
- Linux/Python 3.12: 538 passed, 6 skipped (Make unavailable in the tools image).
- Ruff format/check and `git diff --check`: passed.
- Real development-stack HD preview: passed, preview-only; no media mutations.
- Live JustWatch movie and 62-episode show quality parsing: passed.
- Independent final review: no Critical, Important or Minor findings.
- Changes remain uncommitted on `codex/streaming-quality` in the managed worktree.
