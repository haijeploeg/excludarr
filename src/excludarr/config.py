"""Configuration models and loading for Excludarr v2."""

import os
import re
from datetime import timedelta
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    PlainValidator,
    ValidationError,
    field_validator,
    model_validator,
)

from excludarr.conditions import (
    LEAVES,
    Condition,
    leaves,
    parse_condition,
    parse_duration,
    parse_size,  # noqa: F401 - re-exported
    required_integrations,
)

ParsedCondition = Annotated[Condition, PlainValidator(parse_condition)]


class ConfigError(ValueError):
    # ValueError subclass so raising it inside a validator surfaces as a ValidationError.
    pass


def _normalize_url(v: str) -> str:
    if not v.startswith(("http://", "https://")):
        raise ConfigError("url must start with http:// or https://")
    return v.rstrip("/")


class Integration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    api_key: str
    verify_ssl: bool = True

    _url = field_validator("url")(_normalize_url)


class PlexIntegration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    token: str
    verify_ssl: bool = True
    leaving_soon_collection: str = "Leaving Soon"

    _url = field_validator("url")(_normalize_url)


class Integrations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    radarr: Integration | None = None
    sonarr: Integration | None = None
    tautulli: Integration | None = None
    seerr: Integration | None = None
    plex: PlexIntegration | None = None

    @model_validator(mode="after")
    def _need_arr(self):
        if not (self.radarr or self.sonarr):
            raise ConfigError("at least one of radarr/sonarr must be configured")
        return self


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locale: str = "en_US"
    providers: list[str] = []


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    target: Literal["radarr", "sonarr"]
    level: Literal["movie", "series", "season", "episode"] | None = None
    when: ParsedCondition
    unless: list[ParsedCondition] = []
    action: Literal["delete", "delete_files", "unmonitor", "monitor", "tag", "import_exclusion"]
    delete_files: bool = False
    import_exclusion: bool = False
    search: bool = False
    tag: str | None = None
    preview: bool = True
    grace_period: timedelta = timedelta(0)
    leaving_soon_collection: bool = False
    enabled: bool = True

    @field_validator("grace_period", mode="before")
    @classmethod
    def _grace(cls, v):
        if isinstance(v, bool) or not isinstance(v, (int, str)):
            raise ValueError("grace_period must be 0 or a duration like '30d' (<int>(h|d|w))")  # noqa: TRY004
        if v == 0 or v == "0":
            return timedelta(0)
        if isinstance(v, int):
            raise ValueError("grace_period must be 0 or a duration like '30d' (<int>(h|d|w))")  # noqa: TRY004
        return parse_duration(v)

    @model_validator(mode="after")
    def _level(self):
        if self.level is None:
            self.level = "movie" if self.target == "radarr" else "season"
        elif (self.level == "movie") != (self.target == "radarr"):
            raise ConfigError(
                f"rule {self.name!r}: level must be 'movie' for radarr and not 'movie' for sonarr"
            )
        for leaf in (x for c in [self.when, *self.unless] for x in leaves(c)):
            spec = LEAVES[leaf.name]
            if spec.targets is not None and self.target not in spec.targets:
                raise ConfigError(
                    f"rule {self.name!r}: condition {leaf.name!r} is only valid for "
                    + "/".join(sorted(spec.targets))
                )
            if spec.levels is not None and self.level not in spec.levels(leaf.params):
                raise ConfigError(
                    f"rule {self.name!r}: condition {leaf.name!r} with {leaf.raw!r} is not "
                    f"valid at level {self.level!r}"
                )
        return self


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: Profile = Profile()
    integrations: Integrations
    rules: list[Rule] = []
    database: str | None = None

    @model_validator(mode="after")
    def _check(self):
        names = [r.name for r in self.rules]
        for n in set(names):
            if names.count(n) > 1:
                raise ConfigError(f"duplicate rule name {n!r}")
        for r in self.rules:
            if r.action == "tag" and not r.tag:
                raise ConfigError(f"rule {r.name!r}: action 'tag' requires 'tag'")
            if r.leaving_soon_collection and not self.integrations.plex:
                raise ConfigError(f"rule {r.name!r}: leaving_soon_collection requires plex")
            if not self.profile.providers and any(
                leaf.name == "streaming" and leaf.params[0] == "my_providers"
                for c in [r.when, *r.unless]
                for leaf in leaves(c)
            ):
                raise ConfigError(
                    f"rule {r.name!r}: streaming uses my_providers but profile.providers is empty"
                )
            needed = set().union(*(required_integrations(c) for c in [r.when, *r.unless]))
            missing = sorted(n for n in needed if getattr(self.integrations, n) is None)
            if missing:
                raise ConfigError(
                    f"rule {r.name!r}: its conditions require {', '.join(missing)}, not configured"
                )
        return self


def find_config_path(explicit: Path | None) -> Path:
    if explicit:
        if not explicit.exists():
            raise ConfigError(f"config file not found: {explicit}")
        return explicit
    candidates = []
    if os.environ.get("EXCLUDARR_CONFIG"):
        candidates.append(Path(os.environ["EXCLUDARR_CONFIG"]))
    candidates += [
        Path("excludarr.yml"),
        Path.home() / ".config/excludarr/excludarr.yml",
        Path("/config/excludarr.yml"),
        Path("/etc/excludarr/excludarr.yml"),
    ]
    for c in candidates:
        if c.exists():
            return c
    raise ConfigError("no config file found; tried: " + ", ".join(str(c) for c in candidates))


def _subst(value):
    """Expand ${VAR} inside parsed string values only.

    Substituting after parsing keeps secrets out of YAML error snippets and
    stops env values from injecting YAML structure.
    """
    if isinstance(value, dict):
        return {k: _subst(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_subst(v) for v in value]
    if not isinstance(value, str):
        return value

    def repl(m: re.Match) -> str:
        if m[1] not in os.environ:
            raise ConfigError(f"environment variable {m[1]} is not set")
        return os.environ[m[1]]

    return re.sub(r"\$\{(\w+)\}", repl, value)


def load_config(path: Path | None) -> tuple[Config, Path]:
    p = find_config_path(path)
    try:
        data = yaml.safe_load(p.read_text()) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"invalid YAML in {p}: {e}") from e
    data = _subst(data)
    try:
        return Config.model_validate(data), p
    except ValidationError as e:
        # include_input=False: never echo values (API keys, tokens) back in the error.
        msg = "; ".join(
            f"{'.'.join(map(str, err['loc'])) or 'config'}: {err['msg']}"
            for err in e.errors(include_input=False)
        )
        raise ConfigError(msg) from e


def database_url(config: Config, config_path: Path) -> str:
    return config.database or f"sqlite:///{config_path.parent / 'excludarr.db'}"
