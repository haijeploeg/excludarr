"""Seed the authenticated test services through their real APIs."""

import json
import sqlite3
import time
from datetime import UTC, datetime
from urllib.parse import quote

from dev import stack
from dev.history import TABLES, build_history


def episode_history(show: dict, episodes: list[dict], section: str) -> list[dict]:
    expected = {(1, 1), (2, 1)}
    found = {}
    for episode in episodes:
        key = (episode.get("parentIndex"), episode.get("index"))
        if key not in expected:
            continue
        if key in found or str(episode.get("grandparentRatingKey")) != str(show["ratingKey"]):
            raise stack.SetupError("Plex episode identity is ambiguous")
        found[key] = episode
    if set(found) != expected:
        raise stack.SetupError("Plex episode scan incomplete; both seeded episodes are required")
    return [
        {
            "rating_key": episode["ratingKey"],
            "title": episode["title"],
            "type": "episode",
            "section": section,
            "grandparent": int(show["ratingKey"]),
            "parent": int(episode["parentRatingKey"]),
            "season": season,
            "episode": number,
            "days": 1 if season == 1 else 90,
        }
        for (season, number), episode in sorted(found.items())
    ]


def seeded_history() -> list[dict]:
    rows = []
    start = 0
    while True:
        response = stack.request(
            "tautulli",
            "GET",
            "/api/v2",
            params={"cmd": "get_history", "length": 1000, "start": start, "grouping": 0},
        )["response"]
        if response.get("result") != "success":
            raise stack.SetupError("Tautulli history read failed")
        data = response["data"]
        page = data["data"]
        rows.extend(row for row in page if row.get("player") == "Excludarr Dev Seed")
        start += len(page)
        if not page or start >= data.get("recordsFiltered", start):
            return rows


def reconcile_history() -> None:
    rows = seeded_history()
    if not rows:
        return
    response = stack.request(
        "tautulli",
        "GET",
        "/api/v2",
        params={"cmd": "delete_history", "row_ids": ",".join(str(row["row_id"]) for row in rows)},
    )["response"]
    if response.get("result") != "success":
        raise stack.SetupError("Tautulli could not remove previous seeded history")
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if not seeded_history():
            return
        time.sleep(1)
    raise stack.SetupError("Tautulli seeded history cleanup timed out")


def history_matches(rows: list[dict], state: dict, now: datetime) -> bool:
    from datetime import timedelta

    expected = {str(item["rating_key"]): item for item in state["items"]}
    if len(rows) != len(expected) or {str(row["rating_key"]) for row in rows} != set(expected):
        return False
    try:
        for row in rows:
            item = expected[str(row["rating_key"])]
            if (
                int(row["user_id"]) != int(state["user"]["id"])
                or row["user"].casefold() != state["user"]["name"].casefold()
                or int(row["date"]) != int((now - timedelta(days=item["days"])).timestamp())
                or float(row.get("watched_status") or 0) < 1
            ):
                return False
            if item["type"] == "episode" and (
                int(row["grandparent_rating_key"]) != int(item["grandparent"])
                or int(row["parent_media_index"]) != item["season"]
                or int(row["media_index"]) != item["episode"]
            ):
                return False
    except (KeyError, TypeError, ValueError):
        return False
    return True


def seed_plex(arr_state: dict) -> dict:
    account = stack.plex_credentials()
    sections = stack.request("plex", "GET", "/library/sections")["MediaContainer"].get(
        "Directory", []
    )
    result = {"items": []}
    for group, kind, external in [("movies", "movie", "tmdb"), ("series", "show", "tvdb")]:
        title = "Excludarr Dev " + group.title()
        folder = str(stack.MEDIA / ("movies" if group == "movies" else "tv"))
        matches = [s for s in sections if s.get("title") == title]
        if len(matches) > 1:
            raise stack.SetupError("Duplicate development Plex libraries")
        if not matches:
            stack.request(
                "plex",
                "POST",
                "/library/sections",
                params={
                    "name": title,
                    "type": kind,
                    "agent": "tv.plex.agents.movie" if kind == "movie" else "tv.plex.agents.series",
                    "scanner": "Plex Movie" if kind == "movie" else "Plex TV Series",
                    "language": "en-US",
                    "location": folder,
                },
            )
            sections = stack.request("plex", "GET", "/library/sections")["MediaContainer"][
                "Directory"
            ]
            matches = [s for s in sections if s.get("title") == title]
        section = matches[0]
        locations = [loc.get("path") for loc in section.get("Location", [])]
        if folder not in locations:
            raise stack.SetupError("Plex development library points to a different media path")
        stack.request("plex", "GET", f"/library/sections/{section['key']}/refresh")
        expected = {
            f"{external}://{item['external_id']}": item
            for item in arr_state[group].values()
            if item["files"]
        }
        deadline = time.monotonic() + 180
        found = {}
        while time.monotonic() < deadline:
            media = stack.request(
                "plex", "GET", f"/library/sections/{section['key']}/all", params={"includeGuids": 1}
            )["MediaContainer"].get("Metadata", [])
            found = {guid["id"]: item for item in media for guid in item.get("Guid", [])}
            if all(guid in found for guid in expected):
                break
            time.sleep(2)
        if not all(guid in found for guid in expected):
            raise stack.SetupError(
                f"Plex {group}: metadata GUID matching incomplete; inspect the local library"
            )
        for guid, fixture in expected.items():
            item = found[guid]
            fixture["plex_key"] = str(item["ratingKey"])
            fixture["plex_section"] = str(section["key"])
            role = fixture["role"]
            if group == "movies" and role in ("watched", "oldwatch"):
                result["items"].append(
                    {
                        "rating_key": item["ratingKey"],
                        "title": item["title"],
                        "type": "movie",
                        "section": section["key"],
                        "days": 1 if role == "watched" else 90,
                    }
                )
            elif group == "series" and role == "episodes":
                deadline = time.monotonic() + 180
                while True:
                    children = stack.request(
                        "plex", "GET", f"/library/metadata/{item['ratingKey']}/allLeaves"
                    )["MediaContainer"].get("Metadata", [])
                    try:
                        history = episode_history(item, children, section["key"])
                        break
                    except stack.SetupError:
                        if time.monotonic() >= deadline:
                            raise
                        time.sleep(2)
                result["items"].extend(history)
    result["username"] = account["username"]
    return result


def seed_tautulli(plex_state: dict) -> None:
    users = stack.request("tautulli", "GET", "/api/v2", params={"cmd": "get_users"})["response"]
    if users.get("result") != "success":
        raise stack.SetupError("Tautulli user sync incomplete")
    user = next(
        (
            u
            for u in users["data"]
            if u.get("username", "").lower() == plex_state["username"].lower()
        ),
        None,
    )
    if user is None:
        raise stack.SetupError("Tautulli has not synced the Plex test user yet")
    plex_state["user"] = {"id": user["user_id"], "name": user["username"]}

    path = stack.VOLUMES / "tautulli/tautulli.db"
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
        schema = {
            table: db.execute("SELECT sql FROM sqlite_master WHERE name=?", (table,)).fetchone()[0]
            for table in TABLES
        }
    state = plex_state | {"schema": schema}
    anchor = stack.CONFIG / "history-anchor.json"
    if not anchor.exists():
        stack.save(anchor, {"at": datetime.now(UTC).isoformat()})
    # shortcut: dates stay anchored until reset; rotate imported fixtures for long-lived test stacks.
    now = datetime.fromisoformat(json.loads(anchor.read_text())["at"])
    build_history(stack.CONFIG / "history-import.db", state, now)
    reconcile_history()
    response = stack.request(
        "tautulli",
        "GET",
        "/api/v2",
        params={
            "cmd": "import_database",
            "app": "tautulli",
            "method": "merge",
            "backup": "true",
            "database_path": "/seed/history-import.db",
        },
    )["response"]
    if response.get("result") != "success":
        raise stack.SetupError("Tautulli history import refused; inspect local logs")
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if history_matches(seeded_history(), state, now):
            print("tautulli: recent/old movie and episode history verified", flush=True)
            return
        time.sleep(1)
    raise stack.SetupError("Tautulli history import timed out")


def ensure_seerr_request(kind: str, tmdb_id: int) -> dict:
    existing = stack.request(
        "seerr", "GET", "/api/v1/request", params={"take": 100, "filter": "all"}
    )["results"]
    matching = [
        r for r in existing if r["media"].get("tmdbId") == tmdb_id and r.get("type") == kind
    ]
    if len(matching) > 1:
        raise stack.SetupError("Seerr fixture has duplicate requests")
    if matching:
        return matching[0]
    detail = stack.request("seerr", "GET", f"/api/v1/{kind}/{tmdb_id}")
    media = detail.get("mediaInfo")
    # Reset only this fixture's Seerr availability so already-scanned seasons can be requested.
    if media:
        stack.request("seerr", "DELETE", f"/api/v1/media/{media['id']}")
    payload = {"mediaId": tmdb_id, "mediaType": kind}
    if kind == "tv":
        payload["seasons"] = [1, 2]
    created = stack.request("seerr", "POST", "/api/v1/request", json=payload)
    if not created.get("id"):
        raise stack.SetupError(
            "Seerr did not create the fixture request; inspect local request settings"
        )
    request = stack.request("seerr", "GET", f"/api/v1/request/{created['id']}")
    if request.get("type") != kind or request.get("media", {}).get("tmdbId") != tmdb_id:
        raise stack.SetupError("Seerr fixture request identity mismatch on readback")
    return request


def seed_seerr(arr_state: dict) -> dict:
    result = {}
    for group, role, kind in [("movies", "grace", "movie"), ("series", "episodes", "tv")]:
        fixture = arr_state[group][role]
        tmdb_id = fixture["external_id"]
        if kind == "tv":
            lookup = stack.request(
                "seerr",
                "GET",
                "/api/v1/search",
                # Seerr requires the query value itself to be URL-encoded.
                params={"query": quote(fixture["title"], safe=""), "page": 1},
            )
            matches = [item for item in lookup["results"] if item.get("mediaType") == "tv"]
            verified = []
            for item in matches:
                detail = stack.request("seerr", "GET", f"/api/v1/tv/{item['id']}")
                if detail.get("externalIds", {}).get("tvdbId") == fixture["external_id"]:
                    verified.append(item["id"])
            if len(verified) != 1:
                raise stack.SetupError("Seerr TV metadata could not be matched uniquely")
            tmdb_id = verified[0]
        request = ensure_seerr_request(kind, tmdb_id)
        result[group] = {
            "request_id": request["id"],
            "media_id": request["media"]["id"],
            "tmdb_id": tmdb_id,
        }
    print("seerr: movie and TV requests seeded", flush=True)
    return result
