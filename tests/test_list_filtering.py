from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from excludarr.facts import Clients, Context
from excludarr.list_config import ProxyList
from excludarr.lists.filtering import decide
from excludarr.lists.items import ListItem


def rule(when, unless=None):
    return ProxyList(
        target="sonarr", sources=["s"], when=when, unless=unless or [], on_unknown="exclude"
    )


@pytest.mark.parametrize(
    "when,unless,item,status",
    [
        ({"year": {"min": 2000}}, [], ListItem("Show", "series"), "excluded"),
        ({"year": {"min": 2000}}, [], ListItem("Show", "series", year=1990), "included"),
        ({"genre": "Drama"}, [], ListItem("Show", "series", genres=frozenset()), "included"),
        ({"genre": "Drama"}, [], ListItem("Show", "series"), "excluded"),
        (
            {"rating": {"source": "tmdb", "min": 7}},
            [],
            ListItem("Show", "series", ratings={"tmdb": 8}),
            "excluded",
        ),
        ({"not": {"genre": "Drama"}}, [], ListItem("Show", "series"), "excluded"),
        (
            {"all": [{"year": {"min": 2000}}, {"genre": "Drama"}]},
            [],
            ListItem("Show", "series", year=1990),
            "included",
        ),
        (
            {"any": [{"year": {"min": 2000}}, {"genre": "Drama"}]},
            [],
            ListItem("Show", "series", year=2020),
            "excluded",
        ),
        (
            {"genre": "Drama"},
            [{"year": {"min": 2000}}],
            ListItem("Show", "series", year=2020),
            "included",
        ),
        (
            {"year": {"min": 2000}},
            [{"genre": "Drama"}],
            ListItem("Show", "series", year=2020),
            "excluded",
        ),
    ],
)
def test_decision(when, unless, item, status):
    result = decide(item, rule(when, unless), SimpleNamespace())
    assert result.status == status


@pytest.mark.parametrize(
    "offers,status",
    [
        ({}, "excluded"),
        ({(1, 1): frozenset()}, "included"),
        ({(1, 1): frozenset({(8, "FLATRATE", None)})}, "excluded"),
        ({(1, 1): frozenset({(8, "FLATRATE", None)}), (1, 2): frozenset()}, "included"),
    ],
)
def test_show_catalog_coverage(monkeypatch, offers, status):
    ctx = Context(
        SimpleNamespace(profile=SimpleNamespace(providers=["Netflix"])),
        Clients(),
        None,
        datetime.now(UTC),
    )
    monkeypatch.setattr(ctx, "_match", lambda *a: "show1")
    monkeypatch.setattr(ctx, "_offers", lambda *a: offers)
    monkeypatch.setattr(ctx, "provider_ids", lambda *a: {8})
    monkeypatch.setattr(ctx, "provider_names", lambda: {8: "Netflix"})
    result = decide(ListItem("Show", "series", tmdb_id=1), rule({"streaming": "my_providers"}), ctx)
    assert result.status == status


@pytest.mark.parametrize(
    "policy,status", [(None, "included"), ("include", "included"), ("exclude", "excluded")]
)
def test_unknown_policy(policy, status):
    data = {"target": "radarr", "sources": ["s"], "when": {"streaming": "my_providers"}}
    if policy is not None:
        data["on_unknown"] = policy
    ctx = SimpleNamespace(streaming=lambda _: None)
    result = decide(ListItem("Movie", "movie", imdb_id="tt1"), ProxyList(**data), ctx)
    assert result.status == status
    assert result.unknown is True


@pytest.mark.parametrize(
    "quality,policy,expected,unknown",
    [
        ("sd", "include", "included", False),
        ("hd", "include", "excluded", False),
        (None, "include", "included", True),
        (None, "exclude", "excluded", True),
    ],
)
def test_list_quality_uses_exclusion_semantics(quality, policy, expected, unknown):
    proxy = ProxyList(
        target="radarr",
        sources=["s"],
        on_unknown=policy,
        when={"streaming": {"providers": ["Netflix"], "min_quality": "hd"}},
    )
    ctx = SimpleNamespace(
        streaming=lambda item: [{(8, "FLATRATE", quality)}], provider_ids=lambda providers: {8}
    )
    result = decide(ListItem("Movie", "movie"), proxy, ctx)
    assert (result.status, result.unknown) == (expected, unknown)


@pytest.mark.parametrize("policy,expected", [("include", "included"), ("exclude", "excluded")])
def test_list_unknown_quality_in_unless(policy, expected):
    proxy = ProxyList(
        target="radarr",
        sources=["s"],
        on_unknown=policy,
        when={"year": {"min": 2000}},
        unless=[{"streaming": {"providers": ["Netflix"], "min_quality": "hd"}}],
    )
    ctx = SimpleNamespace(
        streaming=lambda item: [{(8, "FLATRATE", None)}], provider_ids=lambda providers: {8}
    )
    result = decide(ListItem("Movie", "movie", year=2020), proxy, ctx)
    assert (result.status, result.unknown) == (expected, True)
