# fully_watched waits for unaired episodes

## Problem

`fully_watched: true` was true for a Sonarr season or series when all aired
episodes were watched. Unaired episodes could still exist. A rule such as
"delete watched season files" runs a season-level `delete_files`. That action
unmonitors every episode of the season, including the unaired ones. The user
then loses future episodes.

## Behaviour (season and series items)

| Unit state | `fully_watched` |
|---|---|
| some aired episode not watched | false |
| all aired episodes watched, unaired episodes exist | unknown |
| all episodes aired and watched | true |
| nothing aired | unknown (unchanged) |

Unaired means `Episode.aired` is false: no air date, or an air date in the
future. Series scope stays `season >= 1`, so specials are ignored. Season scope
is the item season. Movie and episode items are unchanged.

## Why unknown and not false

"Monitor again" rules use `unless: fully_watched: true`. False would let such a
rule re-monitor and re-download watched episodes. Unknown never acts in `when`
and never acts in `unless`. A rule with this condition waits for the finale.

Only `fully_watched` becomes unknown. `WatchStats` is still returned, so
`play_count`, `not_watched_for`, `watched_within`, `watched_by` and
`requester_watched_more_than` work for a still-airing season. Preview shows the
reason "Unaired episodes remain".

## Compatibility

This changes the meaning of an existing condition. A still-airing season that
matched before no longer matches until its last episode airs and is watched.
