# Manual Development Configuration Implementation Plan

Spec: docs/superpowers/specs/2026-11-11-manual-dev-config-design.md (approved in conversation).
Inline execution; no commits or additional approval rounds for the approved scope.

- [x] Add the tracked YAML covering every condition/action family with preview defaults,
  fixed test endpoints and manual.db. Test config validation, leaf/action coverage and secrets.
- [x] Add dev/cli.py for private env injection, fixed-config/origin validation, shell/CLI
  exec and authenticated local feed reads. Write boundary tests before implementation.
- [x] Bind YAML into tools and daemon; route both through the launcher. Remove CONFIG
  selection from Make, add explicit daemon/feed shortcuts. Test actual Make forwarding.
- [x] Replace dev guide with user scenarios and separate automation notes. Verify live
  config edits, previews, reversible actions, queue/rescue, HTTP/daemon and fixture recovery.
- [x] Run full pytest/lint/Compose rendering, independent final review, fix substantive
  findings with tests, and leave preview defaults and no running manual daemon.

Review focus: optional credentials, config overrides/foreign origins, shared daemon/CLI
locks, preserving edits on seed, and defaults that execute no library mutation.

Implementation result: one tracked, directory-bound YAML, private credential launcher,
checked shell wrapper, shared CLI/daemon manual.db and scenario guide delivered.
490 pytest passed; lint/format/Compose checks passed. Real checks covered atomic file
edits without rebuild, tag, queue/rescue/exceptions, preserved YAML on seed, live
streaming/metadata/watch/request previews, manual daemon/status, authenticated normal
and strict feeds, default-preview no-op and shell guard revalidation. Independent
review findings fixed; no deferred minors. Daemon stopped, preview defaults restored,
no commits. External account-dependent catalogs remain optional/unverified.
