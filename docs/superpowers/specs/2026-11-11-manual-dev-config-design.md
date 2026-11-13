# One manual development configuration

Approved in conversation: expose one editable `dev/excludarr.yml` for all manual
CLI and daemon scenarios; changes apply without rebuilding. All rules default to
preview. Real actions use the normal product workflow: change one rule's preview
flag and run it by name. Include streaming, all action types, condition families,
Sonarr levels, watch/request facts, grace/Plex/rescue/exceptions, lists and scheduling.
Provide commands, expected outcomes, recovery and explicit credential requirements
for optional cloud catalogs. Automated tests retain generated internal configs.

Use a read-only bind mount of the tracked YAML, environment placeholders for private
volume credentials, and a small development-only launcher. The launcher uses the
same YAML and manual state database for shell, CLI and daemon; validates integration
origins against the test services and refuses config overrides. Optional provider
keys come from the ignored local env file. Never print keys, rewrite the user's YAML,
commit, or connect mutations to a personal library. Keep deterministic test configs
and their databases separate from manual state. Seed restores fixtures but preserves
manual YAML/state and account setup; document exception removal when repeating tests.

Approaches: generated per-mode configs were rejected for manual use because they
hide the user-facing configuration and require CONFIG selection. One tracked manual
config plus a scenario guide was chosen by the user. Internal generated configs
remain appropriate for deterministic integration tests.
