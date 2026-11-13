"""Rule conditions: parse from YAML, describe, and evaluate with three-valued logic.

`evaluate` returns True, False or None (unknown). Unknown never becomes True.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from excludarr.facts import Context
    from excludarr.items import MediaItem

from excludarr.lists.items import ListItem

log = logging.getLogger(__name__)

_DURATION = re.compile(r"(\d+)([hdw])")
_SIZE = re.compile(r"(\d+(?:\.\d+)?)(MB|GB|TB)")
_UNITS = {"h": "hours", "d": "days", "w": "weeks"}
_SIZES = {"MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
MONETIZATIONS = ("flatrate", "free", "ads", "rent", "buy")
QUALITY_RANK = {"sd": 0, "hd": 1, "4k": 2}


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


@dataclass(frozen=True)
class Evidence:
    condition: str
    result: bool
    observed: dict[str, Any]
    label: str = ""


@dataclass(frozen=True)
class Observation:
    result: bool
    values: dict[str, Any]


class UnknownReason(StrEnum):
    NOT_REQUESTED = "Not requested"
    SEERR_UNAVAILABLE = "Seerr request data unavailable"
    WATCH_UNAVAILABLE = "Watch history unavailable"
    OTHER = "Other unavailable data"


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


def _streaming(v: Any) -> tuple[list[str] | str, frozenset[str], str | None]:
    if v == "my_providers":
        v = {}
    d = (
        v
        if isinstance(v, dict) and set(v) <= {"providers", "monetization", "min_quality"}
        else None
    )
    if d is None:
        raise ValueError(
            f"expected 'my_providers' or {{providers, monetization, min_quality}}, got {v!r}"
        )
    providers = d.get("providers", "my_providers")
    if providers != "my_providers" and not (
        isinstance(providers, list) and providers and all(isinstance(p, str) for p in providers)
    ):
        raise ValueError(f"providers must be 'my_providers' or a list, got {providers!r}")
    mons = _strs(d.get("monetization", ["flatrate"]))
    if not mons <= set(MONETIZATIONS):
        raise ValueError(f"monetization must be from {list(MONETIZATIONS)}, got {sorted(mons)}")
    minimum = d.get("min_quality")
    if "min_quality" in d and (not isinstance(minimum, str) or minimum not in QUALITY_RANK):
        raise ValueError("min_quality must be sd, hd or 4k")
    return providers, frozenset(m.upper() for m in mons), minimum


# --- evaluators ------------------------------------------------------------


def _in_range(x: float | None, rng: tuple[float | None, float | None]) -> bool | None:
    if x is None:
        return None
    lo, hi = rng
    return (lo is None or x >= lo) and (hi is None or x <= hi)


def _field(name: str, compare: Callable):
    def ev(p, item: MediaItem, ctx: Context) -> Observation | None:
        value = getattr(item, name)
        if isinstance(item, ListItem) and value is None:
            return None
        result = compare(p, value, ctx)
        if result is None:
            return None
        if isinstance(value, datetime):
            return Observation(
                result,
                {
                    name: value.isoformat(),
                    "age_seconds": int((ctx.now - value).total_seconds()),
                },
            )
        elif isinstance(value, frozenset):
            value = sorted(value)
        return Observation(result, {name: value})

    return ev


def _rating_eval(p, item: MediaItem, ctx: Context) -> Observation | None:
    source, *rng = p
    source = source if item.kind == "movie" or isinstance(item, ListItem) else "sonarr"
    rating = (item.ratings or {}).get(source)
    result = _in_range(rating, tuple(rng))
    return None if result is None else Observation(result, {"source": source, "rating": rating})


def _streaming_eval(p, item: MediaItem, ctx: Context) -> Observation | None:
    units = ctx.streaming(item)
    if units is None:
        return None
    providers, mons, minimum = p
    ids = ctx.provider_ids(providers) if units else set()
    if ids is None:
        return None
    qualified, states = [], []
    for unit in units:
        eligible = {(pid, kind, q) for pid, kind, q in unit if pid in ids and kind in mons}
        matches = {
            (pid, kind, q)
            for pid, kind, q in eligible
            if minimum is None or (q is not None and QUALITY_RANK[q] >= QUALITY_RANK[minimum])
        }
        qualified.append(matches)
        states.append(
            True
            if matches
            else None
            if minimum and any(q is None for _, _, q in eligible)
            else False
        )
    if False not in states and None in states:
        return None
    offers = sorted(
        {offer for unit in qualified for offer in unit},
        key=lambda offer: (offer[0], offer[1], offer[2] or ""),
    )
    names = ctx.provider_names() if offers and hasattr(ctx, "provider_names") else {}
    return Observation(
        bool(units) and all(state is True for state in states),
        {
            "min_quality": minimum,
            "matched_offers": [
                {"provider_id": pid, "type": kind, "quality": quality}
                | ({"provider": names[pid]} if pid in names else {})
                for pid, kind, quality in offers
            ],
            "covered_units": sum(bool(unit) for unit in qualified),
            "total_units": len(units),
        },
    )


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _watch(fn: Callable, observed: Callable):
    def ev(p, item: MediaItem, ctx: Context) -> Observation | None:
        w = ctx.watch(item)
        return None if w is None else Observation(fn(p, w, ctx), observed(p, w, ctx))

    return ev


def _watch_age(p, w, ctx):
    return {
        "last_played_at": _timestamp(w.last_watched),
        "age_seconds": (ctx.now - w.last_watched).total_seconds() if w.last_watched else None,
        "threshold_seconds": p.total_seconds(),
    }


def _requests(fn: Callable, observed: Callable):
    def ev(p, item: MediaItem, ctx: Context) -> Observation | UnknownReason:
        reqs = ctx.requests(item)
        if reqs is None:
            return UnknownReason.SEERR_UNAVAILABLE
        if not reqs:
            return UnknownReason.NOT_REQUESTED
        return Observation(fn(p, reqs, ctx), observed(p, reqs, ctx))

    return ev


def _request_age(p, reqs, ctx):
    newest = _newest(reqs)
    return {
        "requested_at": newest.isoformat(),
        "age_seconds": (ctx.now - newest).total_seconds(),
        "threshold_seconds": p.total_seconds(),
    }


def _requester_watched_more_than(p, item: MediaItem, ctx: Context) -> Observation | UnknownReason:
    reqs = ctx.requests(item)
    if reqs is None:
        log.debug("Requester watch for %r: unknown (Seerr request data unavailable)", item.title)
        return UnknownReason.SEERR_UNAVAILABLE
    if not reqs:
        log.debug(
            "Requester watch for %r: unknown (no matching Seerr request, TMDB=%s TVDB=%s)",
            item.title,
            item.tmdb_id,
            item.tvdb_id,
        )
        return UnknownReason.NOT_REQUESTED
    latest = max(reqs, key=lambda r: r.created_at)
    w = ctx.watch(item)
    if w is None:
        log.debug("Requester watch for %r: unknown (watch history unavailable)", item.title)
        return UnknownReason.WATCH_UNAVAILABLE
    seen = [w.last_by_user[n] for n in latest.requested_by if n in w.last_by_user]
    if not seen:
        log.debug("Requester watch for %r: no completed play linked to the requester", item.title)
        return Observation(False, {"requester": latest.requester_name, "last_played_at": None})
    last_play = max(seen)
    age = ctx.now - last_play
    log.debug("Requester watch for %r: last play age %s, required age > %s", item.title, age, p)
    return Observation(
        age > p,
        {
            "requester": latest.requester_name,
            "last_played_at": last_play.isoformat(),
            "age_seconds": age.total_seconds(),
            "threshold_seconds": p.total_seconds(),
        },
    )


def _newest(reqs) -> Any:
    return max(r.created_at for r in reqs)


# --- registry --------------------------------------------------------------

TAUTULLI = frozenset({"tautulli", "plex"})
SEERR = frozenset({"seerr"})


@dataclass(frozen=True)
class LeafSpec:
    parse: Callable[[Any], Any]
    evaluate: Callable[[Any, MediaItem, Context], bool | Observation | UnknownReason | None]
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
    quality = f", min {d['min_quality'].upper()}" if "min_quality" in d else ""
    return f"on {where} ({', '.join(m.lower() for m in mons)}{quality})"


def _list_label(v: Any) -> str:
    return v if isinstance(v, str) else ", ".join(v)


def _range_label(v: dict) -> str:
    return " ".join(f"{k} {v[k]}" for k in ("source", "min", "max") if k in v)


LEAVES: dict[str, LeafSpec] = {
    "added_more_than": LeafSpec(
        parse_duration,
        _field("added", lambda p, v, c: None if v is None else c.now - v > p),
        lambda v: f"added more than {v} ago",
    ),
    "added_less_than": LeafSpec(
        parse_duration,
        _field("added", lambda p, v, c: None if v is None else c.now - v < p),
        lambda v: f"added less than {v} ago",
    ),
    "size_more_than": LeafSpec(
        parse_size, _field("size_bytes", lambda p, v, c: v > p), lambda v: f"larger than {v}"
    ),
    "size_less_than": LeafSpec(
        parse_size, _field("size_bytes", lambda p, v, c: v < p), lambda v: f"smaller than {v}"
    ),
    "tag": LeafSpec(
        _strs,
        _field("tags", lambda p, v, c: bool(p & {t.lower() for t in v})),
        lambda v: f"tagged {_list_label(v)}",
    ),
    "genre": LeafSpec(
        _strs,
        _field("genres", lambda p, v, c: bool(p & {g.lower() for g in v})),
        lambda v: f"genre {_list_label(v)}",
    ),
    "year": LeafSpec(
        _range, _field("year", lambda p, v, c: _in_range(v, p)), lambda v: f"year {_range_label(v)}"
    ),
    "rating": LeafSpec(_rating, _rating_eval, lambda v: f"rating {_range_label(v)}"),
    "monitored": LeafSpec(
        _bool,
        _field("monitored", lambda p, v, c: v == p),
        lambda v: "monitored" if v else "not monitored",
    ),
    "has_file": LeafSpec(
        _bool,
        _field("has_file", lambda p, v, c: v == p),
        lambda v: "has file" if v else "has no file",
    ),
    "status": LeafSpec(
        _status,
        _field("ended", lambda p, v, c: None if v is None else v == p),
        lambda v: f"series {v}",
        targets=frozenset({"sonarr"}),
    ),
    "keep_latest": LeafSpec(
        _keep_latest,
        _field("rank_from_latest", lambda p, v, c: v is not None and v >= p[1]),
        lambda v: "not among the latest " + " ".join(f"{n} {u}" for u, n in v.items()),
        targets=frozenset({"sonarr"}),
        levels=lambda p: {p[0].removesuffix("s")},
    ),
    "streaming": LeafSpec(_streaming, _streaming_eval, _streaming_label),
    "not_watched_for": LeafSpec(
        parse_duration,
        _watch(lambda p, w, c: w.last_watched is None or c.now - w.last_watched > p, _watch_age),
        lambda v: f"not watched for {v}",
        TAUTULLI,
    ),
    "watched_within": LeafSpec(
        parse_duration,
        _watch(
            lambda p, w, c: w.last_watched is not None and c.now - w.last_watched <= p, _watch_age
        ),
        lambda v: f"watched within {v}",
        TAUTULLI,
    ),
    "watched_by": LeafSpec(
        _user,
        _watch(
            lambda p, w, c: p in w.last_by_user,
            lambda p, w, c: {"user": p, "last_played_at": _timestamp(w.last_by_user.get(p))},
        ),
        lambda v: f"watched by {v}",
        TAUTULLI,
    ),
    "play_count": LeafSpec(
        _range,
        _watch(
            lambda p, w, c: _in_range(w.play_count, p), lambda p, w, c: {"play_count": w.play_count}
        ),
        lambda v: f"play count {_range_label(v)}",
        TAUTULLI,
    ),
    "fully_watched": LeafSpec(
        _bool,
        _watch(
            lambda p, w, c: w.fully_watched == p, lambda p, w, c: {"fully_watched": w.fully_watched}
        ),
        lambda v: "fully watched" if v else "not fully watched",
        TAUTULLI,
    ),
    "requested_by": LeafSpec(
        _user,
        _requests(
            lambda p, reqs, c: any(p in r.requested_by for r in reqs),
            lambda p, reqs, c: {"matched_requests": [r.id for r in reqs if p in r.requested_by]},
        ),
        lambda v: f"requested by {v}",
        SEERR,
    ),
    "requested_more_than": LeafSpec(
        parse_duration,
        _requests(lambda p, reqs, c: c.now - _newest(reqs) > p, _request_age),
        lambda v: f"requested more than {v} ago",
        SEERR,
    ),
    "requested_less_than": LeafSpec(
        parse_duration,
        _requests(lambda p, reqs, c: c.now - _newest(reqs) < p, _request_age),
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


def evaluate(
    cond: Condition,
    item: MediaItem,
    ctx: Context,
    *,
    unknown_reasons: set[UnknownReason] | None = None,
    evidence: list[Evidence] | None = None,
) -> bool | None:
    if isinstance(cond, Leaf):
        result = LEAVES[cond.name].evaluate(cond.params, item, ctx)
        if isinstance(result, Observation):
            if evidence is not None:
                evidence.append(Evidence(cond.name, result.result, result.values, describe(cond)))
            return result.result
        if isinstance(result, UnknownReason):
            if unknown_reasons is not None:
                unknown_reasons.add(result)
            return None
        if result is None and unknown_reasons is not None:
            unknown_reasons.add(UnknownReason.OTHER)
        return result
    if isinstance(cond, Not):
        v = evaluate(cond.child, item, ctx, unknown_reasons=unknown_reasons, evidence=evidence)
        return None if v is None else not v
    decisive = isinstance(cond, Any_)  # True decides Any_, False decides All
    unknown = False
    reasons = set() if unknown_reasons is not None else None
    proof = []
    for c in cond.children:
        child_proof = [] if evidence is not None else None
        v = evaluate(c, item, ctx, unknown_reasons=reasons, evidence=child_proof)
        if v is decisive:
            if evidence is not None and child_proof:
                evidence.extend(child_proof)
            return decisive
        if child_proof:
            proof.extend(child_proof)
        unknown = unknown or v is None
    if not unknown and evidence is not None:
        evidence.extend(proof)
    if unknown and unknown_reasons is not None and reasons:
        unknown_reasons.update(reasons)
    return None if unknown else not decisive
