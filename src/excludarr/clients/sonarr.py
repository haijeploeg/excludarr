"""Sonarr v3 API client."""

from excludarr.clients.http import HttpClient
from excludarr.config import Integration


class SonarrClient:
    def __init__(self, cfg: Integration, http: HttpClient | None = None):
        self.http = http or HttpClient(
            "sonarr", f"{cfg.url}/api/v3", {"X-Api-Key": cfg.api_key}, verify=cfg.verify_ssl
        )

    def series(self) -> list[dict]:
        return self.http.get("/series")

    def get_series_by_id(self, series_id: int) -> dict:
        return self.http.get(f"/series/{series_id}")

    def episodes(self, series_id: int) -> list[dict]:
        return self.http.get("/episode", params={"seriesId": series_id})

    def episode_files(self, series_id: int) -> list[dict]:
        return self.http.get("/episodefile", params={"seriesId": series_id})

    def tags(self) -> dict[int, str]:
        return {t["id"]: t["label"] for t in self.http.get("/tag")}

    def ensure_tag(self, label: str) -> int:
        # Sonarr lowercases tag labels, so compare case-insensitively.
        for tag_id, existing in self.tags().items():
            if existing.lower() == label.lower():
                return tag_id
        return self.http.post("/tag", json={"label": label})["id"]

    def update_series(self, series: dict) -> None:
        self.http.put(f"/series/{series['id']}", json=series)

    def delete_series(self, series_id: int, delete_files: bool, add_exclusion: bool) -> None:
        self.http.delete(
            f"/series/{series_id}",
            params={
                "deleteFiles": str(delete_files).lower(),
                "addImportListExclusion": str(add_exclusion).lower(),
            },
        )

    def delete_episode_files(self, file_ids: list[int]) -> None:
        self.http.delete("/episodefile/bulk", json={"episodeFileIds": file_ids})

    def set_episodes_monitored(self, episode_ids: list[int], monitored: bool) -> None:
        self.http.put("/episode/monitor", json={"episodeIds": episode_ids, "monitored": monitored})

    def add_exclusion(self, tvdb_id: int, title: str) -> None:
        self.http.post("/importlistexclusion", json={"tvdbId": tvdb_id, "title": title})

    def search(
        self, series_id: int, season: int | None = None, episode_ids: list[int] | None = None
    ) -> None:
        if episode_ids is not None:
            if not episode_ids:
                return  # empty list is a no-op, never a whole-series search
            body = {"name": "EpisodeSearch", "episodeIds": episode_ids}
        elif season is not None:
            body = {"name": "SeasonSearch", "seriesId": series_id, "seasonNumber": season}
        else:
            body = {"name": "SeriesSearch", "seriesId": series_id}
        self.http.post("/command", json=body)

    def queue(self) -> list[dict]:
        return self.http.get("/queue", params={"pageSize": 1000})["records"]

    def remove_queue_item(self, queue_id: int) -> None:
        self.http.delete(
            f"/queue/{queue_id}", params={"removeFromClient": "true", "blocklist": "false"}
        )
