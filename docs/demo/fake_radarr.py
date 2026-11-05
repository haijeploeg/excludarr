"""Minimal fake Radarr API serving a canned library, used to record the README demo."""

import json
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

GB = 1024**3


def _movie(i, title, year, tmdb, days, size_gb, tags=()):
    added = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    return {
        "id": i,
        "title": title,
        "year": year,
        "tmdbId": tmdb,
        "added": added,
        "sizeOnDisk": int(size_gb * GB),
        "hasFile": True,
        "monitored": True,
        "tags": list(tags),
        "genres": [],
        "ratings": {},
    }


MOVIES = [
    _movie(1, "The Irishman", 2019, 398978, 420, 18.4),
    _movie(2, "Glass Onion", 2022, 661374, 300, 9.1),
    _movie(3, "Dune", 2021, 438631, 250, 21.7),
    _movie(4, "Oppenheimer", 2023, 872585, 200, 24.3, tags=[1]),
    _movie(5, "The Gray Man", 2022, 725201, 380, 11.2),
    _movie(6, "Blade Runner 2049", 2017, 335984, 900, 19.8),
    _movie(7, "Everything Everywhere All at Once", 2022, 545611, 150, 12.6),
    _movie(8, "Knives Out", 2019, 546554, 700, 10.4),
]
TAGS = [{"id": 1, "label": "keep"}]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        body = {"/api/v3/movie": MOVIES, "/api/v3/tag": TAGS}.get(path)
        self.send_response(200 if body is not None else 404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body if body is not None else {}).encode())

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 7878), Handler).serve_forever()
