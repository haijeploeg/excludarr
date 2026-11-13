from datetime import UTC, datetime

import pytest

from excludarr.config import Config
from excludarr.execution import execute_feed, execute_rules
from excludarr.facts import Clients, Context
from excludarr.locking import WorkBusy, execution_lock
from excludarr.storage.repo import Repo


def test_execution_guard_leaves_data_unchanged(tmp_path):
    config = Config.model_validate(
        {
            "database": f"sqlite:///{tmp_path}/db",
            "integrations": {"radarr": {"url": "http://r", "api_key": "key"}},
        }
    )
    repo = Repo(config.database)
    ctx = Context(config, Clients(), repo, datetime.now(UTC))
    with execution_lock(config.database):
        with pytest.raises(WorkBusy):
            execute_rules(ctx, dry_run=False)
        with pytest.raises(WorkBusy):
            execute_feed(config, "movies", repo, ctx.now)
        assert execute_rules(ctx, dry_run=True) == []
    assert repo.history() == []


def test_clients_close_owned_transports():
    from types import SimpleNamespace

    from excludarr.clients.http import HttpClient

    http = HttpClient("test", "http://unused", {})
    clients = Clients(radarr=SimpleNamespace(http=http))
    clients.close()
    assert http._client.is_closed
