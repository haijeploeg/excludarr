import pytest


@pytest.fixture
def minimal_cfg():
    return {
        "integrations": {
            "radarr": {"url": "http://radarr:7878", "api_key": "k"},
            "sonarr": {"url": "http://sonarr:8989", "api_key": "k"},
        }
    }
