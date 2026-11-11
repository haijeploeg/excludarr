"""Read-only, authenticated HTTP access to published list snapshots."""

import hmac
import json
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from sqlalchemy.exc import SQLAlchemyError

from excludarr.config import Config, ConfigError
from excludarr.lists.service import fingerprint, snapshot_valid
from excludarr.storage.repo import Repo


def make_server(config: Config, repo: Repo, host: str, port: int) -> HTTPServer:
    if config.list_proxy is None:
        raise ConfigError("list_proxy is not configured")
    # The running server deliberately uses fixed configuration; edits require restart.
    config = config.model_copy(deep=True)
    proxy = config.list_proxy
    key = proxy.api_key.get_secret_value().encode()
    expected = {slug: fingerprint(config, slug) for slug in proxy.lists}

    class Handler(BaseHTTPRequestHandler):
        timeout = 10

        def log_message(self, format, *args):
            pass  # Request lines contain the feed API key.

        def _reply(self, code, value):
            body = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _handle(self):
            try:
                url = urlsplit(self.path)
                params = parse_qs(url.query, keep_blank_values=True, max_num_fields=20)
            except ValueError:
                self._reply(400, {"error": "Invalid request"})
                return
            keys = params.get("apikey", [])
            if len(keys) != 1 or not hmac.compare_digest(keys[0].encode(), key):
                self._reply(401, {"error": "Unauthorized"})
                return
            if self.command != "GET":
                self._reply(405, {"error": "Method not allowed"})
                return
            prefix = "/lists/"
            slug = url.path[len(prefix) :] if url.path.startswith(prefix) else ""
            if slug not in expected:
                self._reply(404, {"error": "List not found"})
                return
            try:
                snapshot = repo.list_snapshot(slug)
                if not snapshot_valid(snapshot, expected[slug], datetime.now(UTC)):
                    self._reply(503, {"error": "No valid snapshot; refresh the list"})
                    return
            except SQLAlchemyError:
                self._reply(503, {"error": "Snapshot unavailable"})
                return
            self._reply(200, snapshot.payload)

        do_GET = _handle
        do_HEAD = _handle
        do_POST = _handle
        do_PUT = _handle
        do_PATCH = _handle
        do_DELETE = _handle
        do_OPTIONS = _handle
        do_TRACE = _handle

    return ThreadingHTTPServer((host, port), Handler)
