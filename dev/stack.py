"""Disposable development stack tooling; never accepts arbitrary service addresses."""

import argparse
import json
import os
import secrets
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

CONFIG = Path("/config")
MEDIA = Path("/media")
SERVICES = {
    "radarr": "http://radarr:7878",
    "sonarr": "http://sonarr:8989",
    "plex": "http://plex:32400",
    "tautulli": "http://tautulli:8181",
    "seerr": "http://seerr:5055",
}
VOLUMES = Path("/services")


class SetupError(ValueError):
    pass


def save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2))
    temporary.chmod(0o600)
    temporary.replace(path)


def identity(directory: Path | None = None) -> dict:
    directory = directory or CONFIG
    path = directory / "identity.json"
    if path.exists():
        result = json.loads(path.read_text())
        if result.get("project") != "excludarr-dev" or not result.get("id"):
            raise SetupError("Development volume identity mismatch; refusing changes")
        return result
    result = {"project": "excludarr-dev", "id": secrets.token_hex(16)}
    save(path, result)
    return result


def credentials() -> dict:
    path = CONFIG / "credentials.json"
    return json.loads(path.read_text()) if path.exists() else {}


def request(service: str, method: str, path: str, **kwargs):
    if (
        service not in SERVICES
        or not path.startswith("/")
        or path.startswith("//")
        or "://" in path
    ):
        raise SetupError("Only fixed development service paths are accepted")
    keys = credentials()
    headers = kwargs.pop("headers", {})
    if service in ("radarr", "sonarr", "seerr"):
        headers["X-Api-Key"] = keys.get(service, "")
    elif service == "plex":
        headers |= {"X-Plex-Token": keys.get("plex", ""), "Accept": "application/json"}
    else:
        kwargs["params"] = dict(kwargs.get("params", {}), apikey=keys.get("tautulli", ""))
    try:
        with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
            response = client.request(method, SERVICES[service] + path, headers=headers, **kwargs)
        if 300 <= response.status_code < 400:
            raise SetupError(f"{service}: redirect refused")
        if response.is_error:
            raise SetupError(f"{service}: HTTP {response.status_code} at {path.split('?')[0]}")
        if not response.content:
            return {}
        return response.json()
    except (httpx.HTTPError, json.JSONDecodeError) as error:
        raise SetupError(f"{service}: request failed ({type(error).__name__})") from None


def wait_ready(service: str, timeout: float = 180) -> None:
    deadline = time.monotonic() + timeout
    path = {
        "radarr": "/ping",
        "sonarr": "/ping",
        "seerr": "/api/v1/settings/public",
        "plex": "/identity",
        "tautulli": "/api/v2?cmd=status",
    }[service]
    while time.monotonic() < deadline:
        try:
            if service == "plex":
                with httpx.Client(timeout=3, trust_env=False) as client:
                    if client.get(SERVICES[service] + path).status_code == 200:
                        return
            else:
                request(service, "GET", path)
                return
        except SetupError:
            pass
        except httpx.HTTPError:
            pass
        time.sleep(min(1, max(0, deadline - time.monotonic())))
    raise SetupError(
        f"{service}: not ready; inspect docker compose -p excludarr-dev logs {service}"
    )


def initialize() -> None:
    marker = identity()
    keys = credentials()
    for name, port in [("radarr", 7878), ("sonarr", 8989)]:
        directory = VOLUMES / name
        directory.mkdir(parents=True, exist_ok=True)
        stamp = directory / ".excludarr-dev.json"
        config = directory / "config.xml"
        if config.exists() and not stamp.exists():
            raise SetupError(f"{name}: unmarked config volume; refusing to adopt it")
        if stamp.exists() and json.loads(stamp.read_text()) != marker:
            raise SetupError(f"{name}: volume identity mismatch")
        if config.exists():
            actual = ET.parse(config).getroot().findtext("ApiKey")
            if not actual or keys.get(name, actual) != actual:
                raise SetupError(f"{name}: saved API key disagrees with marked config")
            keys[name] = actual
        else:
            keys.setdefault(name, secrets.token_hex(16))
        save(CONFIG / "credentials.json", keys)
        save(stamp, marker)
        if not config.exists():
            root = ET.Element("Config")
            for key, value in {
                "ApiKey": keys[name],
                "Port": str(port),
                "BindAddress": "*",
                "AuthenticationMethod": "External",
                "AuthenticationRequired": "DisabledForLocalAddresses",
                "InstanceName": "excludarr-dev-" + ("Sonarr" if name == "sonarr" else name),
                "LaunchBrowser": "False",
                "UpdateMechanism": "Docker",
            }.items():
                ET.SubElement(root, key).text = value
            temporary = config.with_suffix(".tmp")
            temporary.write_text(ET.tostring(root, encoding="unicode"))
            temporary.replace(config)
        save(stamp, marker)
    for directory in [MEDIA, VOLUMES / "seerr"]:
        directory.mkdir(parents=True, exist_ok=True)
        os.chown(directory, 1000, 1000)
    save(CONFIG / "credentials.json", keys)
    print("Development volumes initialized; no daemon started.")


def prepare_arr(service: str) -> None:
    marker = identity()
    stamp = VOLUMES / service / ".excludarr-dev.json"
    if not stamp.exists() or json.loads(stamp.read_text()) != marker:
        raise SetupError(f"{service}: volume identity mismatch")
    wait_ready(service)
    status = request(service, "GET", "/api/v3/system/status")
    if status.get("instanceName") == "excludarr-dev-" + (
        "Sonarr" if service == "sonarr" else service
    ):
        return
    kind = "movie" if service == "radarr" else "series"
    if status.get("instanceName") != service.capitalize() or request(
        service, "GET", "/api/v3/" + kind
    ):
        raise SetupError(f"{service}: nonempty or foreign instance; refusing bootstrap")
    host = request(service, "GET", "/api/v3/config/host")
    host["instanceName"] = "excludarr-dev-" + ("Sonarr" if service == "sonarr" else service)
    host["allowedHosts"] = service + ",localhost,127.0.0.1"
    request(service, "PUT", "/api/v3/config/host", json=host)


def plex_credentials() -> dict:
    paths = list((VOLUMES / "plex").glob("**/Preferences.xml"))
    if len(paths) != 1:
        raise SetupError("Claim Plex locally at http://localhost:32410/web; see dev/README.md")
    plex = ET.parse(paths[0]).getroot().attrib
    if not plex.get("PlexOnlineToken") or not plex.get("PlexOnlineUsername"):
        raise SetupError("Claim Plex using your TEST account; see dev/README.md")
    machine_id = plex.get("ProcessedMachineIdentifier") or plex.get("MachineIdentifier")
    if not machine_id:
        raise SetupError("Plex server identity missing")
    save(CONFIG / "credentials.json", credentials() | {"plex": plex["PlexOnlineToken"]})
    return {"machine_id": machine_id, "username": plex["PlexOnlineUsername"]}


def refresh_credentials() -> dict:
    import configparser

    account = plex_credentials()
    tautulli = configparser.ConfigParser(interpolation=None)
    tautulli.read(VOLUMES / "tautulli/config.ini")
    if not tautulli.get("PMS", "pms_token", fallback=""):
        raise SetupError("Complete Tautulli wizard at http://localhost:18181 using plex:32400")
    if tautulli.get("PMS", "pms_identifier", fallback="") != account["machine_id"]:
        raise SetupError("Tautulli must point to this development Plex server")
    seerr_path = VOLUMES / "seerr/settings.json"
    if not seerr_path.exists():
        raise SetupError("Complete Seerr setup at http://localhost:15055")
    seerr = json.loads(seerr_path.read_text())
    if seerr.get("plex", {}).get("ip") != "plex":
        raise SetupError("Complete Seerr setup using Plex hostname plex, port 32400")
    for service in ("radarr", "sonarr"):
        for server in seerr.get(service, []):
            if server.get("hostname") != service:
                raise SetupError(
                    "Seerr contains a non-development Arr server; remove it before seeding"
                )
    keys = credentials() | {
        "tautulli": tautulli.get("General", "api_key", fallback=""),
        "seerr": seerr.get("main", {}).get("apiKey", ""),
    }
    if not keys["tautulli"] or not keys["seerr"]:
        raise SetupError("Finish Tautulli and Seerr API setup; see dev/README.md")
    save(CONFIG / "credentials.json", keys)
    return account


def verify_stack(*, full: bool) -> dict:
    marker = identity()
    for name in ("radarr", "sonarr"):
        stamp = VOLUMES / name / ".excludarr-dev.json"
        if not stamp.exists() or json.loads(stamp.read_text()) != marker:
            raise SetupError(f"{name}: volume identity mismatch")
        status = request(name, "GET", "/api/v3/system/status")
        if status.get("instanceName") != "excludarr-dev-" + (
            "Sonarr" if name == "sonarr" else name
        ):
            raise SetupError(f"{name}: server identity mismatch")
    if full:
        account = refresh_credentials()
        server = request("plex", "GET", "/")["MediaContainer"]
        if server.get("machineIdentifier") != account["machine_id"]:
            raise SetupError("Plex server identity mismatch")
        if not all(credentials().get(name) for name in ("plex", "tautulli", "seerr")):
            raise SetupError(
                "Complete local Plex/Tautulli/Seerr setup; see dev/README.md, then seed again"
            )
    return marker


def validate_manifest(manifest: dict) -> None:
    import re

    if manifest.get("version") != 1:
        raise SetupError("Unsupported fixture manifest version")
    for group in ("movies", "series"):
        seen = set()
        for fixture in manifest[group]:
            if not re.fullmatch(r"[a-z][a-z0-9-]*", fixture["role"]):
                raise SetupError("Unsafe fixture path")
            if type(fixture["id"]) is not int or fixture["id"] < 1 or fixture["id"] in seen:
                raise SetupError("Invalid or duplicate fixture ID")
            seen.add(fixture["id"])


def command(service: str, name: str, **fields) -> None:
    result = request(service, "POST", "/api/v3/command", json={"name": name, **fields})
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        status = request(service, "GET", f"/api/v3/command/{result['id']}")
        if status["status"] == "completed":
            return
        if status["status"] in ("failed", "aborted"):
            raise SetupError(f"{service}: {name} failed; inspect service logs")
        time.sleep(1)
    raise SetupError(f"{service}: {name} timed out")


def ensure_arr_item(service: str, fixture: dict) -> dict:
    import shutil
    import subprocess

    movie = service == "radarr"
    kind, external, lookup = ("movie", "tmdbId", "tmdb") if movie else ("series", "tvdbId", "tvdb")
    root = MEDIA / ("movies" if movie else "tv")
    path = root / fixture["role"]
    path.mkdir(parents=True, exist_ok=True)
    for directory in (root, path):
        directory.chmod(0o777)
    items = request(service, "GET", "/api/v3/" + kind)
    existing = next((item for item in items if item.get(external) == fixture["id"]), None)
    tags = request(service, "GET", "/api/v3/tag")
    label = "dev-" + fixture["role"]
    tag = next((tag for tag in tags if tag["label"] == label), None)
    if tag is None:
        tag = request(service, "POST", "/api/v3/tag", json={"label": label})
    exclusion_path = "/api/v3/" + ("exclusions" if movie else "importlistexclusion")
    for exclusion in request(service, "GET", exclusion_path):
        if exclusion.get(external) == fixture["id"]:
            request(service, "DELETE", f"{exclusion_path}/{exclusion['id']}")
    if existing:
        if Path(existing["path"]) != path or tag["id"] not in existing.get("tags", []):
            raise SetupError(f"{service}: fixture ownership mismatch")
        existing["monitored"] = fixture.get("monitored", True)
        existing["tags"] = [tag["id"]]
        if not movie:
            for season in existing.get("seasons", []):
                season["monitored"] = season["seasonNumber"] > 0
        request(service, "PUT", f"/api/v3/{kind}/{existing['id']}", json=existing)
        item = existing
    else:
        matches = request(
            service, "GET", f"/api/v3/{kind}/lookup", params={"term": f"{lookup}:{fixture['id']}"}
        )
        item = next((match for match in matches if match.get(external) == fixture["id"]), None)
        if item is None:
            raise SetupError(f"{service}: fixture metadata unavailable")
        profiles = request(service, "GET", "/api/v3/qualityprofile")
        if not profiles:
            raise SetupError(f"{service}: no quality profiles")
        roots = request(service, "GET", "/api/v3/rootfolder")
        if not any(folder["path"] == str(root) for folder in roots):
            request(service, "POST", "/api/v3/rootfolder", json={"path": str(root)})
        item |= {
            "qualityProfileId": profiles[0]["id"],
            "rootFolderPath": str(root),
            "path": str(path),
            "monitored": fixture.get("monitored", True),
            "tags": [tag["id"]],
        }
        item["addOptions"] = (
            {"searchForMovie": False}
            if movie
            else {
                "searchForMissingEpisodes": False,
                "searchForCutoffUnmetEpisodes": False,
                "monitor": "all",
            }
        )
        if not movie:
            item["seasonFolder"] = True
        item = request(service, "POST", "/api/v3/" + kind, json=item)
    result = {
        "id": item["id"],
        "external_id": fixture["id"],
        "path": str(path),
        "role": fixture["role"],
        "title": item["title"],
        "imdb": item.get("imdbId"),
        "tag": tag["id"],
        "files": [],
    }
    if not movie:
        (path / ".plexmatch").write_text(f"tvdbid: {fixture['id']}\n")
    if not fixture.get("file", True):
        return result
    clip = MEDIA / "clip.mkv"
    if not clip.exists():
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "testsrc=size=320x180:rate=24",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=48000",
                "-t",
                "12",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                str(clip),
            ],
            check=True,
        )
    safe_title = "".join(c if c.isalnum() or c in " -" else "_" for c in item["title"])
    episodes = [None] if movie else [1, 2]
    for season in episodes:
        folder = path if movie else path / f"Season {season:02}"
        folder.mkdir(parents=True, exist_ok=True)
        folder.chmod(0o777)
        suffix = f"({item['year']})" if movie else f"S{season:02}E01"
        video = folder / f"{safe_title} {suffix} WEBDL-1080p.mkv"
        if not video.exists():
            shutil.copyfile(clip, video)
        video.chmod(0o666)
        result["files"].append(str(video))
    command(
        service,
        "RescanMovie" if movie else "RefreshSeries",
        **({"movieId": item["id"]} if movie else {"seriesId": item["id"]}),
    )
    endpoint = "/api/v3/moviefile" if movie else "/api/v3/episodefile"
    imported = request(
        service, "GET", endpoint, params={("movieId" if movie else "seriesId"): item["id"]}
    )
    if not imported:
        raise SetupError(f"{service}: generated media was not imported for role {fixture['role']}")
    return result


def seed_arr(manifest: dict) -> dict:
    validate_manifest(manifest)
    verify_stack(full=False)
    state = {"version": manifest["version"], "identity": identity(), "movies": {}, "series": {}}
    for group, service in [("movies", "radarr"), ("series", "sonarr")]:
        wait_ready(service)
        for fixture in manifest[group]:
            state[group][fixture["role"]] = ensure_arr_item(service, fixture)
            save(CONFIG / "state.json", state)
            print(f"{service}: {fixture['role']} seeded", flush=True)
    return state


def write_configs(state: dict, directory: Path, *, full: bool) -> None:
    import copy

    import yaml

    from excludarr.config import Config

    keys = credentials()
    keys.setdefault("feed", secrets.token_hex(24))
    if directory == CONFIG:
        save(CONFIG / "credentials.json", keys)
    integrations = {
        name: {"url": SERVICES[name], "api_key": keys[name]} for name in ("radarr", "sonarr")
    }
    if full:
        integrations |= {
            name: {"url": SERVICES[name], "api_key": keys[name]} for name in ("tautulli", "seerr")
        }
        integrations["plex"] = {
            "url": SERVICES["plex"],
            "token": keys["plex"],
            "leaving_soon_collection": "Excludarr Dev Leaving Soon",
        }
    rules = []
    definitions = [
        ("delete", "radarr", "delete", "delete"),
        ("files", "radarr", "delete_files", "files"),
        ("monitor", "radarr", "monitor", "monitor"),
        ("unmonitor", "radarr", "unmonitor", "unmonitor"),
        ("tag", "radarr", "tag", "tag"),
        ("grace", "radarr", "delete_files", "grace"),
        ("episode-files", "sonarr", "delete_files", "episodes"),
        ("season-unmonitor", "sonarr", "unmonitor", "seasons"),
        ("season-monitor", "sonarr", "monitor", "seasons"),
        ("series-exclusion", "sonarr", "import_exclusion", "episodes"),
    ]
    for name, target, action, role in definitions:
        rule = {
            "name": name,
            "target": target,
            "action": action,
            "preview": False,
            "when": {"tag": "dev-" + role},
            "unless": [{"tag": "dev-protected"}],
        }
        if target == "sonarr":
            rule["level"] = "episode" if name == "episode-files" else "season"
            if name == "series-exclusion":
                rule["level"] = "series"
        if action == "tag":
            rule["tag"] = "dev-checked"
        if name == "delete":
            rule |= {"delete_files": True, "import_exclusion": True}
        if name == "grace":
            rule["grace_period"] = "1h"
            rule["leaving_soon_collection"] = full
        rules.append(rule)
    if full:
        for role, condition in [
            ("watched", {"watched_within": "7d"}),
            ("oldwatch", {"not_watched_for": "30d"}),
        ]:
            rules.append(
                {
                    "name": role,
                    "target": "radarr",
                    "action": "tag",
                    "tag": "dev-history-ok",
                    "preview": False,
                    "when": {"all": [{"tag": "dev-" + role}, condition]},
                    "unless": [{"tag": "dev-protected"}],
                }
            )
    config = {
        "profile": {"locale": "nl_NL", "providers": ["Netflix"]},
        "integrations": integrations,
        "rules": rules,
        "scheduler": {"timezone": "Europe/Amsterdam"},
        "database": f"sqlite:///{directory}/actions.db",
        "list_proxy": {
            "api_key": keys["feed"],
            "sources": {"fixture": {"type": "stevenlu", "url": "http://fixtures:8000/movies.json"}},
            "lists": {
                "movies": {
                    "target": "radarr",
                    "sources": ["fixture"],
                    "when": {"year": {"min": 1900}},
                    "on_unknown": "include",
                    "schedule": "* * * * *",
                }
            },
        },
    }
    directory.mkdir(parents=True, exist_ok=True)
    for name in ("actions", "preview", "fixture-preview", "daemon"):
        document = copy.deepcopy(config)
        if name in ("preview", "fixture-preview"):
            document["database"] = f"sqlite:///{directory}/{name}.db"
            for rule in document["rules"]:
                rule["preview"] = True
        if name == "preview":
            for index, (target, level, suffix) in enumerate(
                [
                    ("radarr", "movie", "movies"),
                    ("sonarr", "series", "series"),
                ]
            ):
                document["rules"].insert(
                    index,
                    {
                        "name": "streaming-" + suffix,
                        "target": target,
                        "level": level,
                        "preview": True,
                        "action": "delete_files",
                        "when": {"all": [{"has_file": True}, {"streaming": "my_providers"}]},
                        "unless": [{"tag": "dev-protected"}],
                    },
                )
        if name == "daemon":
            for rule in document["rules"]:
                rule["schedule"] = "* * * * *"
        Config.model_validate(document)
        path = directory / f"{name}.yml"
        path.write_text(yaml.safe_dump(document, sort_keys=False))
        path.chmod(0o600)
    feed = [
        {"title": item["title"], "imdb_id": item["imdb"]}
        for item in state["movies"].values()
        if item.get("imdb")
    ]
    (directory / "feed.json").write_text(json.dumps(feed))


def seed(*, arr_only: bool = False) -> dict:
    manifest = json.loads(Path(__file__).with_name("fixtures.json").read_text())
    state = seed_arr(manifest)
    if not arr_only:
        verify_stack(full=True)
        from dev.companions import seed_plex, seed_seerr, seed_tautulli

        state["plex"] = seed_plex(state)
        save(CONFIG / "state.json", state)
        seed_tautulli(state["plex"])
        state["seerr"] = seed_seerr(state)
        save(CONFIG / "state.json", state)
    write_configs(state, CONFIG, full=not arr_only)
    print("Seed verified; preview/action/daemon configs written. No daemon started.", flush=True)
    return state


def setup_plex() -> None:
    from dev.companions import seed_plex

    plex_credentials()
    state = seed(arr_only=True)
    state["plex"] = seed_plex(state)
    save(CONFIG / "state.json", state)
    print("Plex libraries ready. Finish the Tautulli and Seerr wizards, then run full seed.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "seed", "setup-plex", "status", "check"])
    parser.add_argument("--arr-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "init":
            initialize()
        else:
            if args.command in ("seed", "setup-plex"):
                for service in ("radarr", "sonarr"):
                    prepare_arr(service)
            verify_stack(full=False)
            if args.command == "setup-plex":
                setup_plex()
            elif args.command == "seed":
                seed(arr_only=args.arr_only)
            elif args.command == "status":
                verify_stack(full=not args.arr_only)
                print("Development identity verified; services: localhost ports in dev/README.md")
            else:
                from dev.checks import run_checks

                results = run_checks(arr_only=args.arr_only)
                for result in results:
                    print(f"{result['status']}: {result['name']} {result['detail']}")
                if any(result["status"] == "failed" for result in results):
                    raise SystemExit(1)
    except (SetupError, OSError, ValueError, KeyError) as error:
        # Avoid upstream response values or configuration in operational errors.
        print(
            str(error) if isinstance(error, SetupError) else type(error).__name__, file=sys.stderr
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    from dev.stack import main as entrypoint

    entrypoint()
