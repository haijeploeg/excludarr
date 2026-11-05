"""Radarr v3 API client."""

from excludarr.clients.http import HttpClient
from excludarr.config import Integration


class RadarrClient:
    def __init__(self, cfg: Integration, http: HttpClient | None = None):
        self.http = http or HttpClient(
            "radarr", f"{cfg.url}/api/v3", {"X-Api-Key": cfg.api_key}, verify=cfg.verify_ssl
        )

    def movies(self) -> list[dict]:
        return self.http.get("/movie")

    def get_movie(self, movie_id: int) -> dict:
        return self.http.get(f"/movie/{movie_id}")

    def tags(self) -> dict[int, str]:
        return {t["id"]: t["label"] for t in self.http.get("/tag")}

    def ensure_tag(self, label: str) -> int:
        for tag_id, existing in self.tags().items():
            if existing.lower() == label.lower():
                return tag_id
        return self.http.post("/tag", json={"label": label})["id"]

    def update_movie(self, movie: dict) -> None:
        self.http.put(f"/movie/{movie['id']}", json=movie)

    def delete_movie(self, movie_id: int, delete_files: bool, add_exclusion: bool) -> None:
        self.http.delete(
            f"/movie/{movie_id}",
            params={
                "deleteFiles": str(delete_files).lower(),
                "addImportExclusion": str(add_exclusion).lower(),
            },
        )

    def movie_files(self, movie_id: int) -> list[dict]:
        return self.http.get("/moviefile", params={"movieId": movie_id})

    def delete_movie_files(self, file_ids: list[int]) -> None:
        self.http.delete("/moviefile/bulk", json={"movieFileIds": file_ids})

    def add_exclusion(self, tmdb_id: int, title: str, year: int) -> None:
        self.http.post(
            "/exclusions", json={"tmdbId": tmdb_id, "movieTitle": title, "movieYear": year}
        )

    def search(self, movie_ids: list[int]) -> None:
        self.http.post("/command", json={"name": "MoviesSearch", "movieIds": movie_ids})

    def queue(self) -> list[dict]:
        return self.http.get("/queue", params={"pageSize": 1000, "includeMovie": "false"})[
            "records"
        ]

    def remove_queue_item(self, queue_id: int) -> None:
        self.http.delete(
            f"/queue/{queue_id}", params={"removeFromClient": "true", "blocklist": "false"}
        )
