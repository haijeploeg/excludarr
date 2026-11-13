# Minimum streaming quality

Design for issue #67. The user chose a fixed minimum quality per streaming
condition, rather than comparison with local file quality. The user approved
this design in conversation; implementation has not started.

## Intent and scope

Only treat an offer as a streaming alternative when its provider, monetization
type and quality meet the configured requirements. Reuse the shared condition
engine for library rules, scheduled rules and proxy lists.

Exclude local-file quality comparisons, automatic quality detection, HDR, audio
formats, separate 720p/1080p thresholds, provider account tiers and UI work.
JustWatch availability describes its catalog; it does not establish the user's
subscription tier or device capabilities.

## Approaches

- **Fixed minimum per streaming condition — selected by the user.** Explicit,
  works for both existing libraries and list entries without local files, and
  fits the current provider/monetization configuration.
- **Compare streaming quality with the local file — not selected.** Requires
  reliable local quality normalization and additional rules for missing files
  and heterogeneous seasons. This is outside the requested feature.

## Configuration

```yaml
when:
  streaming:
    providers: [Netflix]
    monetization: [flatrate]
    min_quality: hd
```

Accept exactly `sd`, `hd` and `4k`, ordered SD < HD < 4K. These are minimums:
`hd` accepts HD and 4K. Omission preserves existing behavior, including the
`streaming: my_providers` shorthand. Invalid values fail configuration validation.
The default remains no quality restriction. No profile-level setting is added.

## Evaluation and unknown data

Provider, monetization and quality must match on the same offer. A 4K purchase
must not make an SD subscription qualify. Multiple offers may qualify; one is
enough for a movie or episode.

Preserve the existing unit selection for seasons and series. Every selected
episode must qualify, but episodes may qualify on different configured providers.
The feature does not change how aired episodes or specials are selected.

When a minimum is configured, an eligible offer with missing or unrecognized
quality cannot establish a match. For each unit:

- A known qualifying offer makes the result true.
- Otherwise, an eligible offer with unknown quality makes the result unknown.
- Otherwise, the result is false, including an empty offer list.

Aggregate units with existing three-valued AND semantics: false wins over
unknown, and true requires all units to be true. Preserve the current false
result for an empty unit list. Without a minimum, unknown quality does not
change availability matching. Existing unknown behavior under `not` is retained.

Library rules keep their existing requirement for a definitely true condition
before acting. Lists retain their configured `on_unknown` policy: the default
`include` may pass an item whose streaming quality is unknown. Document this
explicitly; do not silently change list defaults.

## Data, cache and output

The existing JustWatch query already requests `presentationType`; a live lookup
confirmed `SD`, `HD` and `_4K`. Preserve this field per offer and normalize `_4K`
to `4k`. Missing and unfamiliar values remain unknown, never guessed.

Update offer consumers and cache serialization together. Version the offer-cache
key so old entries without quality are refetched on next use. No database schema
migration or change to the title-match cache is needed. Keep the existing TTL.
Include the new configuration in proxy-list snapshot fingerprints so snapshots
created with a different minimum are not served as if they matched the new rule.

Condition labels and preview evidence show the requested minimum and qualifying
offer qualities. JSON/YAML reports include the same evidence. Keep ordinary
provider context readable and avoid counting one episode multiple times when a
provider has several quality variants. Unknown quality is reported as unknown.

## Verification and documentation

Cover configuration compatibility, quality ordering, mixed-provider and mixed-
monetization offers, missing/unknown quality, and three-valued negation. Test
season coverage, cache serialization/key invalidation and list unknown policies.
Test snapshot fingerprint changes and output evidence. Exercise the shared daemon
execution path without destructive actions.

Update the README, list-proxy guide and examples. Add a preview-only manual dev
scenario, retaining an unrestricted streaming example. Verify parsing against
live JustWatch movie and episode responses using only read requests; catalog
availability must not become a deterministic test expectation.

Implementation uses the current Python standard library and existing dependencies.
No new dependency, automatic commit, push or production-library mutation is needed.
