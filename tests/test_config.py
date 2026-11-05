from datetime import timedelta

import pytest
from pydantic import ValidationError

from excludarr.config import (
    Config,
    ConfigError,
    Integration,
    database_url,
    find_config_path,
    load_config,
    parse_duration,
    parse_size,
)


def test_parse_duration():
    assert parse_duration("30d") == timedelta(days=30)
    assert parse_duration("2w") == timedelta(weeks=2)
    with pytest.raises(ValueError):
        parse_duration("30")


def test_parse_size():
    assert parse_size("1.5GB") == int(1.5 * 1024**3)


def test_url_normalized():
    assert Integration(url="http://radarr:7878/", api_key="k").url == "http://radarr:7878"


def test_url_without_scheme_rejected():  # old issue #83
    with pytest.raises(ValidationError, match="http://"):
        Integration(url="192.168.0.10:7878", api_key="k")


def test_sonarr_rule_defaults_to_season(minimal_cfg):
    minimal_cfg["rules"] = [
        {"name": "r", "target": "sonarr", "action": "unmonitor", "when": {"monitored": True}}
    ]
    rule = Config.model_validate(minimal_cfg).rules[0]
    assert rule.level == "season" and rule.preview is True and rule.grace_period == timedelta(0)


def test_level_must_match_target(minimal_cfg):
    base = {"name": "r", "action": "unmonitor", "when": {"monitored": True}}
    minimal_cfg["rules"] = [{**base, "target": "radarr", "level": "season"}]
    with pytest.raises(ValidationError):
        Config.model_validate(minimal_cfg)
    minimal_cfg["rules"] = [{**base, "target": "sonarr", "level": "movie"}]
    with pytest.raises(ValidationError):
        Config.model_validate(minimal_cfg)
    minimal_cfg["rules"] = [{**base, "target": "radarr", "grace_period": "0d"}]
    rule = Config.model_validate(minimal_cfg).rules[0]
    assert rule.level == "movie" and rule.grace_period == timedelta(0)


def test_duplicate_rule_names_rejected(minimal_cfg):
    r = {"name": "r", "target": "radarr", "action": "unmonitor", "when": {"monitored": True}}
    minimal_cfg["rules"] = [r, dict(r)]
    with pytest.raises(ValidationError, match="duplicate"):
        Config.model_validate(minimal_cfg)


def test_tag_action_requires_tag(minimal_cfg):
    minimal_cfg["rules"] = [
        {"name": "r", "target": "radarr", "action": "tag", "when": {"monitored": True}}
    ]
    with pytest.raises(ValidationError, match="requires 'tag'"):
        Config.model_validate(minimal_cfg)
    minimal_cfg["rules"][0]["tag"] = "old"
    assert Config.model_validate(minimal_cfg).rules[0].tag == "old"


def test_leaving_soon_requires_plex(minimal_cfg):
    minimal_cfg["rules"] = [
        {
            "name": "r",
            "target": "radarr",
            "action": "delete",
            "leaving_soon_collection": True,
            "when": {"monitored": True},
        }
    ]
    with pytest.raises(ValidationError, match="plex"):
        Config.model_validate(minimal_cfg)


def test_requires_radarr_or_sonarr():
    with pytest.raises(ValidationError):
        Config.model_validate({"integrations": {}})


def test_env_substitution(tmp_path, monkeypatch):
    f = tmp_path / "excludarr.yml"
    f.write_text("integrations:\n  radarr:\n    url: http://r:7878\n    api_key: ${RADARR_KEY}\n")
    monkeypatch.delenv("RADARR_KEY", raising=False)
    with pytest.raises(ConfigError, match="RADARR_KEY"):
        load_config(f)
    monkeypatch.setenv("RADARR_KEY", "secret")
    cfg, path = load_config(f)
    assert cfg.integrations.radarr.api_key == "secret" and path == f
    assert database_url(cfg, path) == f"sqlite:///{tmp_path / 'excludarr.db'}"


def test_invalid_config_raises_config_error(tmp_path):
    f = tmp_path / "c.yml"
    f.write_text("integrations: {}\n")
    with pytest.raises(ConfigError):
        load_config(f)


def test_find_config_path_order(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("EXCLUDARR_CONFIG", raising=False)
    cwd_file = tmp_path / "excludarr.yml"
    env_file = tmp_path / "env.yml"
    explicit = tmp_path / "explicit.yml"
    for f in (cwd_file, env_file, explicit):
        f.write_text("")
    monkeypatch.setenv("EXCLUDARR_CONFIG", str(env_file))
    assert find_config_path(explicit) == explicit
    assert find_config_path(None) == env_file
    monkeypatch.delenv("EXCLUDARR_CONFIG")
    assert find_config_path(None).resolve() == cwd_file.resolve()
    cwd_file.unlink()
    home_file = tmp_path / "home/.config/excludarr/excludarr.yml"
    home_file.parent.mkdir(parents=True)
    home_file.write_text("")
    assert find_config_path(None) == home_file


@pytest.mark.parametrize("bad", [30, False, True, 1.5, "30"])
def test_grace_period_rejects_ambiguous(minimal_cfg, bad):
    minimal_cfg["rules"] = [
        {
            "name": "r",
            "target": "radarr",
            "action": "unmonitor",
            "grace_period": bad,
            "when": {"monitored": True},
        }
    ]
    with pytest.raises(ValidationError, match="grace_period"):
        Config.model_validate(minimal_cfg)


@pytest.mark.parametrize("zero", [0, "0", "0d"])
def test_grace_period_zero(minimal_cfg, zero):
    minimal_cfg["rules"] = [
        {
            "name": "r",
            "target": "radarr",
            "action": "unmonitor",
            "grace_period": zero,
            "when": {"monitored": True},
        }
    ]
    assert Config.model_validate(minimal_cfg).rules[0].grace_period == timedelta(0)


def test_unknown_keys_rejected(minimal_cfg):
    minimal_cfg["rules"] = [
        {"name": "r", "target": "radarr", "action": "delete", "unles": [{"x": 1}]}
    ]
    with pytest.raises(ValidationError, match="unles"):
        Config.model_validate(minimal_cfg)
    with pytest.raises(ValidationError, match="bogus"):
        Integration(url="http://a", api_key="k", bogus=1)


def test_invalid_yaml_is_config_error(tmp_path):
    f = tmp_path / "c.yml"
    f.write_text("a: [unclosed\n")
    with pytest.raises(ConfigError, match="invalid YAML"):
        load_config(f)


def test_explicit_missing_path_raises(tmp_path):
    with pytest.raises(ConfigError, match="config file not found"):
        find_config_path(tmp_path / "nope.yml")


def test_validation_error_does_not_leak_secrets(tmp_path):
    f = tmp_path / "c.yml"
    f.write_text(
        "integrations:\n  plex: {url: 'http://plex:32400', token: SUPERSECRET}\n"
        "  tautulli: {url: 'http://t:8181', api_key: SUPERSECRET}\n"
    )
    with pytest.raises(ConfigError) as e:
        load_config(f)
    assert "SUPERSECRET" not in str(e.value) and "radarr/sonarr" in str(e.value)
    f.write_text(
        "integrations:\n  radarr: {url: 'http://r:7878', api_key: SUPERSECRET}\n"
        "rules:\n  - {name: r, target: radarr, action: tag, when: {monitored: true}}\n"
    )
    with pytest.raises(ConfigError, match="requires 'tag'") as e:
        load_config(f)
    assert "SUPERSECRET" not in str(e.value)


@pytest.mark.parametrize(
    "streaming",
    ["my_providers", {"monetization": "free"}, {"providers": "my_providers"}],
)
@pytest.mark.parametrize("where", ["when", "unless"])
def test_my_providers_requires_profile_providers(minimal_cfg, streaming, where):
    r = {"name": "r", "target": "radarr", "action": "unmonitor", "when": {"monitored": True}}

    def put(v):
        r[where] = {"streaming": v} if where == "when" else [{"streaming": v}]

    put(streaming)
    minimal_cfg["rules"] = [r]
    with pytest.raises(ValidationError, match="rule 'r'.*profile.providers"):
        Config.model_validate(minimal_cfg)
    minimal_cfg["profile"] = {"providers": ["Netflix"]}
    Config.model_validate(minimal_cfg)
    # An explicit provider list does not need profile.providers.
    put({"providers": ["Netflix"]})
    minimal_cfg["profile"] = {}
    Config.model_validate(minimal_cfg)
