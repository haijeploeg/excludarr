"""Plex client (library lookup by GUID, collection membership)."""

from dataclasses import dataclass
from typing import Literal

from excludarr.clients.http import HttpClient
from excludarr.config import PlexIntegration

TYPE_IDS = {"movie": 1, "show": 2, "season": 3, "episode": 4}


@dataclass
class PlexItem:
    rating_key: str
    section_key: str
    type: Literal["movie", "show", "season", "episode"]


class PlexClient:
    def __init__(self, cfg: PlexIntegration, http: HttpClient | None = None):
        self.http = http or HttpClient(
            "plex",
            cfg.url,
            {"X-Plex-Token": cfg.token, "Accept": "application/json"},
            verify=cfg.verify_ssl,
        )

    def items_by_guid(self) -> dict[tuple[str, str], PlexItem]:
        """Keyed by (type, guid): TMDB/TVDB number movies and shows separately."""
        out: dict[tuple[str, str], PlexItem] = {}
        sections = self.http.get("/library/sections")["MediaContainer"].get("Directory", [])
        for s in sections:
            if s["type"] not in TYPE_IDS:
                continue
            data = self.http.get(f"/library/sections/{s['key']}/all", params={"includeGuids": 1})
            for m in data["MediaContainer"].get("Metadata", []):
                item = PlexItem(str(m["ratingKey"]), str(s["key"]), s["type"])
                for g in m.get("Guid", []):
                    out[(item.type, g["id"])] = item

        return out

    def season(self, show: PlexItem, number: int) -> PlexItem | None:
        return self._child(show, "children", "season", index=number)

    def episode(self, show: PlexItem, season: int, number: int) -> PlexItem | None:
        return self._child(show, "allLeaves", "episode", parentIndex=season, index=number)

    def _child(self, show: PlexItem, path: str, kind, **match) -> PlexItem | None:
        data = self.http.get(f"/library/metadata/{show.rating_key}/{path}")
        for m in data["MediaContainer"].get("Metadata", []):
            if all(m.get(k) == v for k, v in match.items()):
                return PlexItem(str(m["ratingKey"]), show.section_key, kind)
        return None

    def _edit(self, item: PlexItem, extra: dict) -> None:
        params = {"type": TYPE_IDS[item.type], "id": item.rating_key, "collection.locked": 1}
        self.http.put(f"/library/sections/{item.section_key}/all", params=params | extra)

    def add_to_collection(self, item: PlexItem, name: str) -> None:
        # Plex replaces the whole collection list on edit, so resend the existing tags too.
        meta = self.http.get(f"/library/metadata/{item.rating_key}")["MediaContainer"]
        tags = [c["tag"] for m in meta.get("Metadata", []) for c in m.get("Collection", [])]
        if name.lower() not in {t.lower() for t in tags}:
            tags.append(name)
        self._edit(item, {f"collection[{i}].tag.tag": t for i, t in enumerate(tags)})

    def remove_from_collection(self, item: PlexItem, name: str) -> None:
        self._edit(item, {"collection[].tag.tag-": name})

    def refresh(self, section_key: str) -> None:
        self.http.get(f"/library/sections/{section_key}/refresh")
