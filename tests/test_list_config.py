import pytest
from pydantic import ValidationError

from excludarr.config import Config, ConfigError, load_config
from excludarr.list_config import ListProxyConfig


def proxy(source=None, **kw):
    return dict(
        api_key="feed-secret",
        sources={"s": source or {"type": "stevenlu"}},
        lists={"movies": {"target": "radarr", "sources": ["s"], "when": {"year": {"min": 2000}}}},
        **kw,
    )


def test_modes_and_secrets():
    p = ListProxyConfig.model_validate(
        proxy({"type": "trakt", "mode": "trending", "media_type": "movie", "client_id": "id"})
    )
    assert p.sources["s"].limit == 100
    assert "feed-secret" not in repr(p)
    assert (
        Config.model_validate(
            {"integrations": {"radarr": {"url": "http://r", "api_key": "k"}}}
        ).list_proxy
        is None
    )


@pytest.mark.parametrize(
    "change",
    [
        {"limit": 0},
        {"limit": 1001},
        {"limit": True},
        {"mode": "discover"},
        {"media_type": None},
        {"list_id": 5},
    ],
)
def test_reject_invalid_chart(change):
    source = {"type": "tmdb", "mode": "popular", "media_type": "movie"} | change
    with pytest.raises(ValidationError):
        ListProxyConfig.model_validate(proxy(source))


@pytest.mark.parametrize(
    "condition",
    [{"has_file": False}, {"size_less_than": "1GB"}, {"rating": {"source": "sonarr", "min": 5}}],
)
def test_reject_library_conditions(condition):
    data = proxy()
    data["lists"]["movies"]["when"] = condition
    with pytest.raises(ValidationError):
        ListProxyConfig.model_validate(data)


def test_reject_references_and_incompatible_sources():
    for source, names, target in [
        ({"type": "stevenlu"}, ["missing"], "radarr"),
        ({"type": "stevenlu"}, ["s"], "sonarr"),
    ]:
        data = proxy(source)
        data["lists"]["movies"].update(sources=names, target=target)
        with pytest.raises(ValidationError):
            ListProxyConfig.model_validate(data)


def test_duplicate_yaml_proxy_names(tmp_path):
    path = tmp_path / "config.yml"
    path.write_text("list_proxy:\n  sources:\n    s: {type: stevenlu}\n    s: {type: stevenlu}\n")
    with pytest.raises(ConfigError, match="duplicate"):
        load_config(path)


def test_yaml_merge_override_remains_supported(tmp_path):
    path = tmp_path / "config.yml"
    path.write_text("""integrations:
  radarr: &arr {url: "http://r", api_key: key}
  sonarr:
    <<: *arr
    url: "http://s"
""")
    config, _ = load_config(path)
    assert config.integrations.sonarr.url == "http://s"


def test_invalid_unknown_policy():
    data = proxy()
    data["lists"]["movies"]["on_unknown"] = "hold"
    with pytest.raises(ValidationError):
        ListProxyConfig.model_validate(data)
