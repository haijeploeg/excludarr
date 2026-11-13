"""Development-only deterministic list source with a bounded blocking test endpoint."""

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/movies.json", "/blocked.json"):
            self.send_error(404)
            return
        if self.path == "/blocked.json":
            time.sleep(8)
        payload = Path("/config/feed.json")
        body = payload.read_bytes() if payload.exists() else json.dumps([]).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
