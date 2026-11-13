"""List refresh orchestration and snapshot compatibility."""

import hashlib
import hmac
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta

from pydantic import BaseModel, SecretStr

from excludarr.config import Config, ConfigError
from excludarr.storage.repo import SnapshotEntry


def fingerprint(config: Config, slug: str) -> str:
    proxy = config.list_proxy
    if proxy is None or slug not in proxy.lists:
        raise ConfigError("unknown outgoing list")
    key = proxy.api_key.get_secret_value().encode()

    def canonical(value):
        if isinstance(value, SecretStr):
            return hmac.new(key, value.get_secret_value().encode(), hashlib.sha256).hexdigest()
        if isinstance(value, BaseModel):
            value = {name: getattr(value, name) for name in type(value).model_fields}
        if is_dataclass(value):
            value = asdict(value)
        if isinstance(value, dict):
            return {k: canonical(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [canonical(v) for v in value]
        if isinstance(value, (set, frozenset)):
            return sorted(canonical(v) for v in value)
        return value

    rule = proxy.lists[slug]
    value = {
        "revision": 1,
        "profile": config.profile,
        "list": {
            name: getattr(rule, name) for name in type(rule).model_fields if name != "schedule"
        },
        "sources": {name: proxy.sources[name] for name in rule.sources},
        "tmdb_token": proxy.tmdb_token,
        "api_key": proxy.api_key,
    }
    body = json.dumps(canonical(value), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(body).hexdigest()


def snapshot_valid(snapshot: SnapshotEntry | None, expected: str, now: datetime) -> bool:
    return bool(
        snapshot
        and snapshot.payload is not None
        and snapshot.successful_at
        and snapshot.fingerprint == expected
        and timedelta(0) <= now - snapshot.successful_at < timedelta(hours=6)
    )


def build_list(config: Config, slug: str, repo, now: datetime) -> dict:
    from excludarr.clients.http import IntegrationError
    from excludarr.clients.justwatch import JustWatchClient
    from excludarr.clients.list_sources import fetch_source
    from excludarr.clients.tmdb import TmdbClient
    from excludarr.conditions import leaves
    from excludarr.facts import Clients, Context
    from excludarr.lists.filtering import ListDecision, decide

    proxy = config.list_proxy
    if proxy is None or slug not in proxy.lists:
        raise ConfigError("unknown outgoing list")
    rule = proxy.lists[slug]
    kind = "movie" if rule.target == "radarr" else "series"
    export_id = "imdb_id" if kind == "movie" else "tvdb_id"
    wanted = {export_id}
    needs_streaming = False
    field_names = {"year": "year", "genre": "genres", "rating": "ratings", "status": "ended"}
    for condition in [rule.when, *rule.unless]:
        for leaf in leaves(condition):
            needs_streaming |= leaf.name == "streaming"
            if leaf.name in field_names:
                wanted.add(field_names[leaf.name])
    jw = JustWatchClient(config.profile.locale)
    ctx = Context(config, Clients(justwatch=jw), repo, now, refresh=True)
    global_token = proxy.tmdb_token.get_secret_value() if proxy.tmdb_token else None
    items, identities = [], {}
    try:
        for source_name in rule.sources:
            source = proxy.sources[source_name]
            token = (
                source.token.get_secret_value()
                if source.type == "tmdb" and source.token
                else global_token
            )
            tmdb = TmdbClient(token) if token else None
            step, current = "fetching source", None
            try:
                incoming = fetch_source(source, tmdb_token=global_token)
                for item in incoming:
                    if item.kind != kind:
                        continue
                    current = item
                    step = "enriching metadata"
                    missing = frozenset(field for field in wanted if getattr(item, field) is None)
                    if needs_streaming and not (item.tmdb_id or item.imdb_id):
                        missing |= {"tmdb_id"}
                    if missing and tmdb:
                        # Identity/metadata are refreshed with the feed, avoiding stale filter decisions.
                        item = tmdb.enrich(item, missing)
                    step = "deduplicating identities"
                    aliases = [
                        (name, getattr(item, name))
                        for name in ("tmdb_id", "imdb_id", "tvdb_id")
                        if getattr(item, name) is not None
                    ]
                    matches = {identities[a] for a in aliases if a in identities}
                    if len(matches) > 1:
                        raise IntegrationError(source_name, "conflicting identities")
                    if matches:
                        index = next(iter(matches))
                        previous = items[index]
                        for name, value in aliases:
                            if getattr(previous, name) not in (None, value):
                                raise IntegrationError(source_name, "conflicting identities")
                            setattr(previous, name, value)
                    else:
                        index = len(items)
                        items.append(item)
                    for alias in aliases:
                        identities[alias] = index
            except IntegrationError as error:
                context = f"list {slug!r}, {step}"
                if current is not None:
                    context += (
                        f" for {current.title!r} (TMDB={current.tmdb_id}, "
                        f"IMDb={current.imdb_id}, TVDB={current.tvdb_id})"
                    )
                reason = f"{context}: {error}"
                secrets = [proxy.api_key, proxy.tmdb_token]
                for configured in proxy.sources.values():
                    secrets.extend([configured.token, configured.client_id])
                for secret in secrets:
                    if secret:
                        reason = reason.replace(secret.get_secret_value(), "[redacted]")
                raise IntegrationError(source_name, reason, error.status) from error
            finally:
                if tmdb:
                    tmdb.http._client.close()
        result = {
            "name": slug,
            "payload": [],
            "items": [],
            "summary": {"included": 0, "excluded": 0},
        }
        for item in items:
            reason = None
            if not getattr(item, export_id):
                decision = ListDecision(item, "excluded", [])
                reason = f"Missing {export_id}; cannot export to {rule.target.title()}"
            else:
                decision = decide(item, rule, ctx)
            result["summary"][decision.status] += 1
            result["items"].append(
                {
                    "title": item.title,
                    "media": item.kind,
                    "ids": {"tmdb": item.tmdb_id, "imdb": item.imdb_id, "tvdb": item.tvdb_id},
                    "decision": decision.status,
                    "unknown": decision.unknown,
                    "reason": reason,
                    "evidence": [asdict(e) for e in decision.evidence],
                }
            )
            if decision.status == "included":
                result["payload"].append(
                    {
                        "title": item.title,
                        "imdb_id" if kind == "movie" else "tvdbId": getattr(item, export_id),
                    }
                )
        return result
    finally:
        jw.http._client.close()


def refresh_list(config: Config, slug: str, repo, now: datetime, *, publish: bool = True) -> dict:
    from excludarr.clients.http import IntegrationError

    # Validate before recording errors; never create failure rows for arbitrary names.
    expected = fingerprint(config, slug)
    try:
        result = build_list(config, slug, repo, now)
    except (IntegrationError, ConfigError) as error:
        if publish:
            repo.list_failure(slug, str(error), now)
        raise
    if publish:
        repo.list_publish(slug, result["payload"], result, expected, now)
    return result
