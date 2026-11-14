from datetime import UTC, datetime, timedelta
from itertools import product

import pytest
from pydantic import ValidationError

from excludarr.clients.seerr import SeerrRequest
from excludarr.conditions import (
    All,
    Any_,
    Leaf,
    Not,
    describe,
    evaluate,
    parse_condition,
    required_integrations,
)
from excludarr.config import Config
from excludarr.facts import WatchStats
from excludarr.items import MediaItem

NOW = datetime(2026, 11, 5, tzinfo=UTC)
PROVIDERS = {"netflix": 8, "prime": 9}


class FakeContext:
    def __init__(self, streaming=None, watch=None, requests=None, my=("netflix",)):
        self._streaming, self._watch, self._requests, self._my = streaming, watch, requests, my
        self.now = NOW

    def streaming(self, item):
        return self._streaming

    def watch(self, item):
        return self._watch

    def requests(self, item):
        return self._requests

    def provider_ids(self, names):
        names = self._my if names == "my_providers" else names
        return {PROVIDERS[n.lower()] for n in names}


def movie(**kw):
    kw.setdefault("key", "radarr:movie:1")
    return MediaItem(kind="movie", title="M (2020)", base_title="M", arr_id=1, **kw)


def season(**kw):
    return MediaItem(
        key="sonarr:season:1:1", kind="season", title="S", base_title="S", arr_id=1, season=1, **kw
    )


def ago(days):
    return NOW - timedelta(days=days)


def watch(last_days=None, by=None, plays=0, full=False, full_by=()):
    return WatchStats(
        last_watched=ago(last_days) if last_days is not None else None,
        play_count=plays,
        fully_watched=full,
        last_by_user={u: ago(d) for u, d in (by or {}).items()},
        fully_watched_by=frozenset(full_by),
    )


def request(days, users=("alice",), rid=1):
    return SeerrRequest(rid, 1, "movie", 1, None, ago(days), frozenset(users), frozenset())


def const(v):
    return Leaf("_const", v)


@pytest.fixture(autouse=True)
def _const_leaf(monkeypatch):
    from excludarr import conditions

    spec = conditions.LeafSpec(
        parse=lambda v: v, evaluate=lambda p, item, ctx: p, label=lambda v: str(v)
    )
    monkeypatch.setitem(conditions.LEAVES, "_const", spec)


V = [True, False, None]


def kleene_and(a, b):
    if a is False or b is False:
        return False
    return None if None in (a, b) else True


def kleene_or(a, b):
    if a is True or b is True:
        return True
    return None if None in (a, b) else False


@pytest.mark.parametrize("a,b", list(product(V, V)))
def test_all_truth_table(a, b):
    assert evaluate(All([const(a), const(b)]), movie(), FakeContext()) is kleene_and(a, b)


@pytest.mark.parametrize("a,b", list(product(V, V)))
def test_any_truth_table(a, b):
    assert evaluate(Any_([const(a), const(b)]), movie(), FakeContext()) is kleene_or(a, b)


@pytest.mark.parametrize("a,expected", [(True, False), (False, True), (None, None)])
def test_not_truth_table(a, expected):
    assert evaluate(Not(const(a)), movie(), FakeContext()) is expected


LITERAL = {
    "any": [
        {"streaming": "my_providers"},
        {"added_more_than": "180d"},
        {"requester_watched_more_than": "30d"},
    ]
}
GROUPED = {
    "any": [
        {"streaming": "my_providers"},
        {"all": [{"added_more_than": "180d"}, {"not_watched_for": "30d"}]},
    ]
}


def test_user_rule_literal_or():
    ctx = FakeContext(streaming=[frozenset()], watch=watch(5, {"alice": 5}), requests=[])
    assert evaluate(parse_condition(LITERAL), movie(added=ago(200)), ctx) is True
    assert evaluate(parse_condition(LITERAL), movie(added=ago(10)), ctx) is None


def test_user_rule_grouped():
    ctx = FakeContext(streaming=[frozenset()], watch=watch(5, {"alice": 5}))
    assert evaluate(parse_condition(GROUPED), movie(added=ago(200)), ctx) is False
    ctx = FakeContext(streaming=[frozenset()], watch=watch(40))
    assert evaluate(parse_condition(GROUPED), movie(added=ago(200)), ctx) is True
    ctx = FakeContext(streaming=[frozenset()], watch=None)
    assert evaluate(parse_condition(GROUPED), movie(added=ago(200)), ctx) is None


def test_streaming_season_requires_every_aired_episode():
    units = [frozenset({(8, "FLATRATE", None)}), frozenset({(9, "FLATRATE", None)})]
    ctx = FakeContext(streaming=units)
    netflix = parse_condition({"streaming": {"providers": ["Netflix"]}})
    both = parse_condition({"streaming": {"providers": ["Netflix", "Prime"]}})
    assert evaluate(netflix, season(), ctx) is False
    assert evaluate(both, season(), ctx) is True


def test_streaming_no_units_is_false_and_unknown_is_none():
    cond = parse_condition({"streaming": "my_providers"})
    assert evaluate(cond, season(), FakeContext(streaming=[])) is False
    assert evaluate(cond, season(), FakeContext(streaming=None)) is None


def test_streaming_monetization_filter():
    ctx = FakeContext(streaming=[frozenset({(8, "FREE", None)})])
    assert evaluate(parse_condition({"streaming": "my_providers"}), movie(), ctx) is False
    cond = parse_condition({"streaming": {"monetization": ["free"]}})
    assert evaluate(cond, movie(), ctx) is True


def test_unknown_streaming_never_true_under_not():
    cond = parse_condition({"not": {"streaming": "my_providers"}})
    assert evaluate(cond, movie(), FakeContext(streaming=None)) is None


def test_keep_latest():
    cond = parse_condition({"keep_latest": {"seasons": 2}})
    ctx = FakeContext()
    assert evaluate(cond, season(rank_from_latest=0), ctx) is False
    assert evaluate(cond, season(rank_from_latest=1), ctx) is False
    assert evaluate(cond, season(rank_from_latest=2), ctx) is True
    assert evaluate(cond, season(rank_from_latest=None), ctx) is False


def test_attribute_leaves():
    ctx = FakeContext()
    m = movie(
        added=ago(10),
        size_bytes=2 * 1024**3,
        tags=frozenset({"Keep"}),
        genres=frozenset({"Drama"}),
        year=2020,
        ratings={"tmdb": 7.5},
        monitored=False,
        has_file=True,
    )
    cases = [
        ({"added_less_than": "30d"}, True),
        ({"added_more_than": "30d"}, False),
        ({"size_more_than": "1GB"}, True),
        ({"size_less_than": "1GB"}, False),
        ({"tag": "keep"}, True),
        ({"genre": ["comedy", "DRAMA"]}, True),
        ({"tag": ["other"]}, False),
        ({"year": {"min": 2020, "max": 2020}}, True),
        ({"year": {"max": 2019}}, False),
        ({"rating": {"min": 7}}, True),
        ({"rating": {"source": "imdb", "min": 7}}, None),
        ({"monitored": False}, True),
        ({"has_file": False}, False),
    ]
    for raw, expected in cases:
        assert evaluate(parse_condition(raw), m, ctx) is expected, raw
    assert evaluate(parse_condition({"added_more_than": "1d"}), movie(), ctx) is None
    s = season(ratings={"sonarr": 8.0}, ended=True)
    assert evaluate(parse_condition({"rating": {"source": "imdb", "min": 8}}), s, ctx) is True
    assert evaluate(parse_condition({"status": "ended"}), s, ctx) is True
    assert evaluate(parse_condition({"status": "continuing"}), s, ctx) is False


def test_watch_leaves():
    ctx = FakeContext(watch=watch(5, {"bob": 5, "alice": 9}, plays=3, full=True, full_by={"bob"}))
    cases = [
        ({"not_watched_for": "30d"}, False),
        ({"watched_within": "30d"}, True),
        ({"watched_by": "Bob"}, True),
        ({"watched_by": "carol"}, False),
        ({"play_count": {"min": 3}}, True),
        ({"play_count": {"max": 2}}, False),
        ({"fully_watched": True}, True),
        ({"fully_watched_by": "BOB"}, True),
        ({"fully_watched_by": "alice"}, False),
    ]
    for raw, expected in cases:
        assert evaluate(parse_condition(raw), movie(), ctx) is expected, raw
    never = FakeContext(watch=watch())
    assert evaluate(parse_condition({"not_watched_for": "30d"}), movie(), never) is True
    assert evaluate(parse_condition({"watched_within": "30d"}), movie(), never) is False
    for raw, _ in cases:
        assert evaluate(parse_condition(raw), movie(), FakeContext()) is None, raw


def test_seerr_leaves():
    reqs = [request(100, ("alice",)), request(10, ("bob", "bob@x"), rid=2)]
    ctx = FakeContext(requests=reqs, watch=watch(40, {"bob@x": 40, "alice": 1}))
    cases = [
        ({"requested_by": "ALICE"}, True),
        ({"requested_by": "carol"}, False),
        ({"requested_more_than": "30d"}, False),  # most recent request is 10d old
        ({"requested_less_than": "30d"}, True),
        ({"requester_watched_more_than": "30d"}, True),  # bob, not alice
        ({"requester_watched_more_than": "60d"}, False),
    ]
    for raw, expected in cases:
        assert evaluate(parse_condition(raw), movie(), ctx) is expected, raw
    for reqs_value in (None, []):
        unknown = FakeContext(requests=reqs_value, watch=watch(40))
        for raw, _ in cases:
            assert evaluate(parse_condition(raw), movie(), unknown) is None, raw
    never = FakeContext(requests=[request(10, ("bob",))], watch=watch(40, {"alice": 40}))
    cond = parse_condition({"requester_watched_more_than": "30d"})
    assert evaluate(cond, movie(), never) is False
    assert evaluate(cond, movie(), FakeContext(requests=[request(10)])) is None


@pytest.mark.parametrize(
    "raw,match",
    [
        ({"bogus": 1}, "bogus"),
        ({"added_more_than": "30"}, "added_more_than"),
        ({"monitored": "yes"}, "monitored"),
        ({"streaming": {"monetization": ["gratis"]}}, "streaming"),
        ({"streaming": {"providers": "Netflix"}}, "streaming"),
        ({"keep_latest": {"years": 1}}, "keep_latest"),
        ({"year": {"from": 2000}}, "year"),
        ({"rating": {"source": "rt"}}, "rating"),
        ({"status": "running"}, "status"),
        ({"all": [{"tag": "a"}, {"nope": 1}]}, "nope"),
        ({"not": {"genre": 5}}, "genre"),
    ],
)
def test_parse_errors_name_the_leaf(raw, match):
    with pytest.raises(ValueError, match=match):
        parse_condition(raw)


@pytest.mark.parametrize("raw", [{}, {"tag": "a", "genre": "b"}, "tag", {"all": []}, {"any": 1}])
def test_parse_rejects_malformed(raw):
    with pytest.raises(ValueError):
        parse_condition(raw)


def test_describe_grouping():
    assert describe(parse_condition({"streaming": "my_providers"})) == "on my providers (flatrate)"
    assert describe(parse_condition({"added_more_than": "180d"})) == "added more than 180d ago"
    assert describe(parse_condition({"not_watched_for": "30d"})) == "not watched for 30d"
    assert (
        describe(parse_condition(GROUPED))
        == "(on my providers (flatrate) or (added more than 180d ago and not watched for 30d))"
    )
    assert describe(parse_condition({"not": {"tag": "keep"}})) == "not tagged keep"


def test_describe_string_monetization():
    c = parse_condition({"streaming": {"monetization": "free"}})
    assert describe(c) == "on my providers (free)"
    c = parse_condition({"streaming": {"providers": ["Netflix"], "monetization": ["free", "ads"]}})
    assert describe(c) == "on Netflix (free, ads)"


def test_required_integrations():
    assert required_integrations(parse_condition(GROUPED)) == {"tautulli", "plex"}
    assert required_integrations(parse_condition(LITERAL)) == {"tautulli", "plex", "seerr"}
    assert required_integrations(parse_condition({"tag": "x"})) == set()


def rule(**kw):
    return {"name": "r1", "target": "radarr", "action": "delete", **kw}


def test_rule_using_tautulli_without_plex_rejected(minimal_cfg):
    minimal_cfg["integrations"]["tautulli"] = {"url": "http://t:8181", "api_key": "k"}
    minimal_cfg["rules"] = [rule(when={"not_watched_for": "30d"})]
    with pytest.raises(ValidationError, match="r1.*plex"):
        Config.model_validate(minimal_cfg)
    minimal_cfg["integrations"]["plex"] = {"url": "http://p:32400", "token": "t"}
    cfg = Config.model_validate(minimal_cfg)
    assert isinstance(cfg.rules[0].when, Leaf)


def test_rule_unless_checked_for_integrations(minimal_cfg):
    minimal_cfg["rules"] = [rule(when={"tag": "x"}, unless=[{"requested_by": "bob"}])]
    with pytest.raises(ValidationError, match="r1.*seerr"):
        Config.model_validate(minimal_cfg)


def test_rule_target_and_level_validated(minimal_cfg):
    minimal_cfg["rules"] = [rule(when={"status": "ended"})]
    with pytest.raises(ValidationError, match="r1.*status"):
        Config.model_validate(minimal_cfg)
    minimal_cfg["rules"] = [rule(target="sonarr", when={"keep_latest": {"episodes": 2}})]
    with pytest.raises(ValidationError, match="r1.*keep_latest"):
        Config.model_validate(minimal_cfg)
    minimal_cfg["rules"] = [rule(target="sonarr", when={"keep_latest": {"seasons": 2}})]
    assert Config.model_validate(minimal_cfg).rules[0].level == "season"
    minimal_cfg["rules"] = [
        rule(target="sonarr", level="series", when={"keep_latest": {"seasons": 2}})
    ]
    with pytest.raises(ValidationError, match="r1.*keep_latest"):
        Config.model_validate(minimal_cfg)


def test_rule_requires_when(minimal_cfg):
    minimal_cfg["rules"] = [rule()]
    with pytest.raises(ValidationError, match="when"):
        Config.model_validate(minimal_cfg)


def test_evidence_uses_only_the_decisive_any_branch():
    condition = parse_condition({"any": [{"year": {"min": 2020}}, {"streaming": "my_providers"}]})
    evidence = []
    ctx = FakeContext(streaming=[frozenset({(8, "FLATRATE", None), (9, "BUY", None)})])
    assert evaluate(condition, movie(), ctx, evidence=evidence) is True
    assert [entry.condition for entry in evidence] == ["streaming"]
    assert evidence[0].observed["matched_offers"] == [
        {"provider_id": 8, "type": "FLATRATE", "quality": None}
    ]


def test_evidence_for_not_and_requester_play():
    evidence = []
    assert (
        evaluate(
            parse_condition({"not": {"monitored": False}}),
            movie(monitored=True),
            FakeContext(),
            evidence=evidence,
        )
        is True
    )
    assert evidence[0].result is False
    evidence.clear()
    ctx = FakeContext(requests=[request(50)], watch=watch(43, {"alice": 43}))
    assert (
        evaluate(
            parse_condition({"requester_watched_more_than": "30d"}), movie(), ctx, evidence=evidence
        )
        is True
    )
    assert evidence[0].observed["last_played_at"] == ago(43).isoformat()
    assert evidence[0].observed["threshold_seconds"] == 30 * 86400


@pytest.mark.parametrize("minimum", ["sd", "hd", "4k"])
@pytest.mark.parametrize("quality", ["sd", "hd", "4k"])
def test_streaming_minimum_ordering(minimum, quality):
    cond = parse_condition({"streaming": {"min_quality": minimum}})
    expected = ["sd", "hd", "4k"].index(quality) >= ["sd", "hd", "4k"].index(minimum)
    assert evaluate(cond, movie(), FakeContext(streaming=[{(8, "FLATRATE", quality)}])) is expected


@pytest.mark.parametrize("invalid", ["SD", "_4K", "1080p", "", None, True, 1])
def test_streaming_min_quality_validation(invalid):
    with pytest.raises(ValueError, match="min_quality"):
        parse_condition({"streaming": {"min_quality": invalid}})


@pytest.mark.parametrize(
    "offers,expected",
    [
        ({(8, "FLATRATE", "sd"), (8, "BUY", "4k")}, False),
        ({(8, "FLATRATE", "sd"), (9, "FLATRATE", "4k")}, False),
        ({(8, "FLATRATE", None), (9, "FLATRATE", "4k")}, None),
        ({(8, "FLATRATE", "sd"), (8, "FLATRATE", None)}, None),
        ({(8, "FLATRATE", "hd"), (8, "FLATRATE", None)}, True),
        ({(8, "FLATRATE", "sd"), (9, "FLATRATE", None)}, False),
        (set(), False),
    ],
)
def test_quality_cannot_be_combined_across_offers(offers, expected):
    cond = parse_condition({"streaming": {"min_quality": "hd"}})
    ctx = FakeContext(streaming=[offers])
    assert evaluate(cond, movie(), ctx) is expected
    assert evaluate(Not(cond), movie(), ctx) is (None if expected is None else not expected)


@pytest.mark.parametrize(
    "qualities,expected",
    [
        (["hd", None], None),
        (["hd", "sd"], False),
        (["sd", None], False),
        (["hd", "4k"], True),
        ([], False),
    ],
)
def test_season_quality_requires_every_selected_episode(qualities, expected):
    cond = parse_condition({"streaming": {"providers": ["netflix", "prime"], "min_quality": "hd"}})
    units = [{(8 if i % 2 else 9, "FLATRATE", q)} for i, q in enumerate(qualities)]
    assert evaluate(cond, season(), FakeContext(streaming=units)) is expected


def test_unrestricted_streaming_accepts_unknown_quality():
    cond = parse_condition({"streaming": "my_providers"})
    assert evaluate(cond, movie(), FakeContext(streaming=[{(8, "FLATRATE", None)}])) is True
