"""Rule conditions: parse from YAML, describe, and evaluate with three-valued logic.

`evaluate` returns True, False or None (unknown). Unknown never becomes True.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from excludarr.facts import Context
    from excludarr.items import MediaItem

_DURATION = re.compile(r"(\d+)([hdw])")
_SIZE = re.compile(r"(\d+(?:\.\d+)?)(MB|GB|TB)")
_UNITS = {"h": "hours", "d": "days", "w": "weeks"}
_SIZES = {"MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
MONETIZATIONS = ("flatrate", "free", "ads", "rent", "buy")


def parse_duration(s: str) -> timedelta:
    m = _DURATION.fullmatch(str(s).strip())
    if not m:
        raise ValueError(f"invalid duration {s!r}, expected <int>(h|d|w) such as '30d'")
    return timedelta(**{_UNITS[m[2]]: int(m[1])})


def parse_size(s: str) -> int:
    m = _SIZE.fullmatch(str(s).strip())
    if not m:
        raise ValueError(f"invalid size {s!r}, expected <number>(MB|GB|TB) such as '1.5GB'")
    return int(float(m[1]) * _SIZES[m[2]])


# --- tree ----------------------------------------------------------------


@dataclass
class All:
    children: list[Condition]


@dataclass
class Any_:
    children: list[Condition]


@dataclass
class Not:
    child: Condition


@dataclass
class Leaf:
    name: str
    params: Any
    raw: Any = field(default=None, repr=False, compare=False)  # as written, for describe()


Condition = All | Any_ | Not | Leaf


# --- param parsers ---------------------------------------------------------


def _bool(v: Any) -> bool:
    if not isinstance(v, bool):
        raise ValueError(f"expected true/false, got {v!r}")  # noqa: TRY004 - pydantic surfaces ValueError
    return v


def _num(v: Any) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"expected a number, got {v!r}")  # noqa: TRY004 - pydantic surfaces ValueError
    return v


def _user(v: Any) -> str:
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f"expected a user name, got {v!r}")
    return v.strip().lower()


def _strs(v: Any) -> frozenset[str]:
    vals = [v] if isinstance(v, str) else v
    if not isinstance(vals, list) or not vals or not all(isinstance(x, str) for x in vals):
        raise ValueError(f"expected a string or a list of strings, got {v!r}")
    return frozenset(x.lower() for x in vals)


def _dict(v: Any, allowed: set[str]) -> dict:
    if not isinstance(v, dict) or not v or not set(v) <= allowed:
        raise ValueError(f"expected a mapping with keys from {sorted(allowed)}, got {v!r}")
    return v


def _range(v: Any) -> tuple[float | None, float | None]:
    d = _dict(v, {"min", "max"})
    return tuple(_num(d[k]) if k in d else None for k in ("min", "max"))


def _rating(v: Any) -> tuple[str, float | None, float | None]:
    d = _dict(v, {"source", "min", "max"})
    source = d.get("source", "tmdb")
    if source not in ("tmdb", "imdb"):
        raise ValueError(f"source must be 'tmdb' or 'imdb', got {source!r}")
    if "min" not in d and "max" not in d:
        raise ValueError("rating needs 'min' and/or 'max'")
    return (source, *_range({k: d[k] for k in ("min", "max") if k in d}))


def _status(v: Any) -> bool:
    if v not in ("ended", "continuing"):
        raise ValueError(f"expected 'ended' or 'continuing', got {v!r}")
    return v == "ended"


def _keep_latest(v: Any) -> tuple[str, int]:
    d = _dict(v, {"seasons", "episodes"})
    (unit, n), *rest = d.items()
    if rest or isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ValueError(f"expected {{seasons: N}} or {{episodes: N}} with N >= 1, got {v!r}")
    return unit, n


def _streaming(v: Any) -> tuple[list[str] | str, frozenset[str]]:
    if v == "my_providers":
        v = {}
    d = v if isinstance(v, dict) and set(v) <= {"providers", "monetization"} else None
    if d is None:
        raise ValueError(f"expected 'my_providers' or {{providers, monetization}}, got {v!r}")
    providers = d.get("providers", "my_providers")
    if providers != "my_providers" and not (
        isinstance(providers, list) and providers and all(isinstance(p, str) for p in providers)
    ):
        raise ValueError(f"providers must be 'my_providers' or a list, got {providers!r}")
    mons = _strs(d.get("monetization", ["flatrate"]))
    if not mons <= set(MONETIZATIONS):
        raise ValueError(f"monetization must be from {list(MONETIZATIONS)}, got {sorted(mons)}")
    return providers, frozenset(m.upper() for m in mons)


# --- evaluators ------------------------------------------------------------


def _in_range(x: float | None, rng: tuple[float | None, float | None]) -> bool | None:
    if x is None:
        return None
    lo, hi = rng
    return (lo is None or x >= lo) and (hi is None or x <= hi)


def _rating_eval(p, item: MediaItem, ctx: Context) -> bool | None:
    source, *rng = p
    return _in_range(item.ratings.get(source if item.kind == "movie" else "sonarr"), tuple(rng))


def _streaming_eval(p, item: MediaItem, ctx: Context) -> bool | None:
    units = ctx.streaming(item)
    if units is None:
        return None
    if not units:
        return False  # nothing aired: never vacuously "on provider"
    providers, mons = p
    ids = ctx.provider_ids(providers)
    return all(any(pid in ids and m in mons for pid, m in u) for u in units)


def _watch(fn: Callable) -> Callable:
    def ev(p, item: MediaItem, ctx: Context) -> bool | None:
        w = ctx.watch(item)
        return None if w is None else fn(p, w, ctx)

    return ev


def _requests(fn: Callable) -> Callable:
    def ev(p, item: MediaItem, ctx: Context) -> bool | None:
        reqs = ctx.requests(item)
        return fn(p, reqs, ctx) if reqs else None

    return ev


def _requester_watched_more_than(p, item: MediaItem, ctx: Context) -> bool | None:
    reqs = ctx.requests(item)
    if not reqs:
        return None  # no request record is unknown, not False (spec §4)
    latest = max(reqs, key=lambda r: r.created_at)
    w = ctx.watch(item)
    if w is None:
        return None
    seen = [w.last_by_user[n] for n in latest.requested_by if n in w.last_by_user]
    return bool(seen) and ctx.now - max(seen) > p


def _newest(reqs) -> Any:
    return max(r.created_at for r in reqs)


# --- registry --------------------------------------------------------------

TAUTULLI = frozenset({"tautulli", "plex"})
SEERR = frozenset({"seerr"})


@dataclass(frozen=True)
class LeafSpec:
    parse: Callable[[Any], Any]
    evaluate: Callable[[Any, MediaItem, Context], bool | None]
    label: Callable[[Any], str]  # renders the raw param
    integrations: frozenset[str] = frozenset()
    targets: frozenset[str] | None = None  # None: any target
    levels: Callable[[Any], set[str]] | None = None  # allowed levels for the parsed params


def _streaming_label(v: Any) -> str:
    d = {} if v == "my_providers" else v
    providers = d.get("providers", "my_providers")
    where = "my providers" if providers == "my_providers" else ", ".join(providers)
    mons = d.get("monetization", ["flatrate"])
    mons = [mons] if isinstance(mons, str) else mons
    return f"on {where} ({', '.join(m.lower() for m in mons)})"


def _list_label(v: Any) -> str:
    return v if isinstance(v, str) else ", ".join(v)


def _range_label(v: dict) -> str:
    return " ".join(f"{k} {v[k]}" for k in ("source", "min", "max") if k in v)


LEAVES: dict[str, LeafSpec] = {
    "added_more_than": LeafSpec(
        parse_duration,
        lambda p, i, c: None if i.added is None else c.now - i.added > p,
        lambda v: f"added more than {v} ago",
    ),
    "added_less_than": LeafSpec(
        parse_duration,
        lambda p, i, c: None if i.added is None else c.now - i.added < p,
        lambda v: f"added less than {v} ago",
    ),
    "size_more_than": LeafSpec(
        parse_size, lambda p, i, c: i.size_bytes > p, lambda v: f"larger than {v}"
    ),
    "size_less_than": LeafSpec(
        parse_size, lambda p, i, c: i.size_bytes < p, lambda v: f"smaller than {v}"
    ),
    "tag": LeafSpec(
        _strs,
        lambda p, i, c: bool(p & {t.lower() for t in i.tags}),
        lambda v: f"tagged {_list_label(v)}",
    ),
    "genre": LeafSpec(
        _strs,
        lambda p, i, c: bool(p & {g.lower() for g in i.genres}),
        lambda v: f"genre {_list_label(v)}",
    ),
    "year": LeafSpec(
        _range, lambda p, i, c: _in_range(i.year, p), lambda v: f"year {_range_label(v)}"
    ),
    "rating": LeafSpec(_rating, _rating_eval, lambda v: f"rating {_range_label(v)}"),
    "monitored": LeafSpec(
        _bool, lambda p, i, c: i.monitored == p, lambda v: "monitored" if v else "not monitored"
    ),
    "has_file": LeafSpec(
        _bool, lambda p, i, c: i.has_file == p, lambda v: "has file" if v else "has no file"
    ),
    "status": LeafSpec(
        _status,
        lambda p, i, c: None if i.ended is None else i.ended == p,
        lambda v: f"series {v}",
        targets=frozenset({"sonarr"}),
    ),
    "keep_latest": LeafSpec(
        _keep_latest,
        lambda p, i, c: i.rank_from_latest is not None and i.rank_from_latest >= p[1],
        lambda v: "not among the latest " + " ".join(f"{n} {u}" for u, n in v.items()),
        targets=frozenset({"sonarr"}),
        levels=lambda p: {p[0].removesuffix("s")},
    ),
    "streaming": LeafSpec(_streaming, _streaming_eval, _streaming_label),
    "not_watched_for": LeafSpec(
        parse_duration,
        _watch(lambda p, w, c: w.last_watched is None or c.now - w.last_watched > p),
        lambda v: f"not watched for {v}",
        TAUTULLI,
    ),
    "watched_within": LeafSpec(
        parse_duration,
        _watch(lambda p, w, c: w.last_watched is not None and c.now - w.last_watched <= p),
        lambda v: f"watched within {v}",
        TAUTULLI,
    ),
    "watched_by": LeafSpec(
        _user, _watch(lambda p, w, c: p in w.last_by_user), lambda v: f"watched by {v}", TAUTULLI
    ),
    "play_count": LeafSpec(
        _range,
        _watch(lambda p, w, c: _in_range(w.play_count, p)),
        lambda v: f"play count {_range_label(v)}",
        TAUTULLI,
    ),
    "fully_watched": LeafSpec(
        _bool,
        _watch(lambda p, w, c: w.fully_watched == p),
        lambda v: "fully watched" if v else "not fully watched",
        TAUTULLI,
    ),
    "requested_by": LeafSpec(
        _user,
        _requests(lambda p, reqs, c: any(p in r.requested_by for r in reqs)),
        lambda v: f"requested by {v}",
        SEERR,
    ),
    "requested_more_than": LeafSpec(
        parse_duration,
        _requests(lambda p, reqs, c: c.now - _newest(reqs) > p),
        lambda v: f"requested more than {v} ago",
        SEERR,
    ),
    "requested_less_than": LeafSpec(
        parse_duration,
        _requests(lambda p, reqs, c: c.now - _newest(reqs) < p),
        lambda v: f"requested less than {v} ago",
        SEERR,
    ),
    "requester_watched_more_than": LeafSpec(
        parse_duration,
        _requester_watched_more_than,
        lambda v: f"requester last watched more than {v} ago",
        SEERR | TAUTULLI,
    ),
}


# --- public API ------------------------------------------------------------


def parse_condition(raw: Any) -> Condition:
    if not isinstance(raw, dict) or len(raw) != 1:
        raise ValueError(f"a condition must be a mapping with exactly one key, got {raw!r}")
    ((name, value),) = raw.items()
    if name in ("all", "any"):
        if not isinstance(value, list) or not value:
            raise ValueError(f"'{name}' needs a non-empty list of conditions, got {value!r}")
        children = [parse_condition(c) for c in value]
        return All(children) if name == "all" else Any_(children)
    if name == "not":
        return Not(parse_condition(value))
    spec = LEAVES.get(name)
    if spec is None:
        raise ValueError(f"unknown condition {name!r}")
    try:
        return Leaf(name, spec.parse(value), value)
    except ValueError as e:
        raise ValueError(f"condition {name!r}: {e}") from e


def leaves(cond: Condition) -> Iterator[Leaf]:
    if isinstance(cond, Leaf):
        yield cond
    elif isinstance(cond, Not):
        yield from leaves(cond.child)
    else:
        for c in cond.children:
            yield from leaves(c)


def required_integrations(cond: Condition) -> set[str]:
    return {i for leaf in leaves(cond) for i in LEAVES[leaf.name].integrations}


def describe(cond: Condition) -> str:
    if isinstance(cond, Leaf):
        return LEAVES[cond.name].label(cond.raw)
    if isinstance(cond, Not):
        return f"not {describe(cond.child)}"
    sep = " and " if isinstance(cond, All) else " or "
    return "(" + sep.join(describe(c) for c in cond.children) + ")"


def evaluate(cond: Condition, item: MediaItem, ctx: Context) -> bool | None:
    if isinstance(cond, Leaf):
        return LEAVES[cond.name].evaluate(cond.params, item, ctx)
    if isinstance(cond, Not):
        v = evaluate(cond.child, item, ctx)
        return None if v is None else not v
    decisive = isinstance(cond, Any_)  # True decides Any_, False decides All
    unknown = False
    for c in cond.children:
        v = evaluate(c, item, ctx)
        if v is decisive:
            return decisive
        unknown = unknown or v is None
    return None if unknown else not decisive
