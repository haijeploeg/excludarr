import json
from datetime import UTC, datetime, timedelta
from http.client import HTTPConnection
from threading import Thread

import pytest

from excludarr.config import Config
from excludarr.lists.server import make_server
from excludarr.lists.service import fingerprint
from excludarr.storage.repo import Repo


@pytest.fixture
def serving(tmp_path):
    config = Config.model_validate(
        {
            "integrations": {"radarr": {"url": "http://r", "api_key": "key"}},
            "list_proxy": {
                "api_key": "secret-€",
                "sources": {"s": {"type": "stevenlu"}},
                "lists": {
                    "movies": {
                        "target": "radarr",
                        "sources": ["s"],
                        "when": {"year": {"min": 2000}},
                    }
                },
            },
        }
    )
    repo = Repo(f"sqlite:///{tmp_path}/db")
    server = make_server(config, repo, "127.0.0.1", 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request(path, method="GET"):
        conn = HTTPConnection(*server.server_address, timeout=2)
        conn.request(method, path)
        response = conn.getresponse()
        result = (response.status, response.read(), dict(response.getheaders()))
        conn.close()
        return result

    yield config, repo, request
    server.shutdown()
    thread.join(2)
    server.server_close()


def test_auth_and_missing_snapshot(serving, capsys):
    _, _, request = serving
    for path in [
        "/lists/movies",
        "/lists/unknown?apikey=wrong",
        "/lists/movies?apikey=secret-%E2%82%AC&apikey=wrong",
    ]:
        assert request(path)[0] == 401
    assert request("/lists/unknown?apikey=secret-%E2%82%AC")[0] == 404
    assert request("/lists/movies?apikey=secret-%E2%82%AC")[0] == 503
    assert request("/lists/movies?apikey=secret-%E2%82%AC", "POST")[0] == 405
    assert "secret-" not in capsys.readouterr().err


def test_valid_empty_expired_and_config_mismatch(serving):
    config, repo, request = serving
    now = datetime.now(UTC)
    path = "/lists/movies?apikey=secret-%E2%82%AC"
    fp = fingerprint(config, "movies")
    repo.list_publish("movies", [], {}, fp, now)
    status, body, headers = request(path)
    assert status == 200 and json.loads(body) == []
    assert int(headers["Content-Length"]) == len(body)
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    repo.list_publish("movies", [{"title": "Example", "imdb_id": "tt0000001"}], {}, fp, now)
    assert json.loads(request(path)[1]) == [{"title": "Example", "imdb_id": "tt0000001"}]
    repo.list_publish("movies", [], {}, fp, now - timedelta(hours=6))
    assert request(path)[0] == 503
    repo.list_publish("movies", [], {}, "different", now)
    assert request(path)[0] == 503
