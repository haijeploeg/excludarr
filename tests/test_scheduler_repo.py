from datetime import UTC, datetime, timedelta

from excludarr.jobs import JobSpec
from excludarr.storage.repo import Repo


def test_scheduler_records_recovery_and_instance_guard(tmp_path):
    repo = Repo(f"sqlite:///{tmp_path}/db")
    now = datetime.now(UTC)
    jobs = [JobSpec(("rule", "same"), "0 2 * * *", 0), JobSpec(("list", "same"), "0 * * * *", 0)]
    repo.scheduler_start("first", jobs, "UTC", now)
    run = repo.job_start("first", ("rule", "same"), now, now)
    repo.scheduler_heartbeat("first", now + timedelta(seconds=5))
    status = repo.scheduler_status()
    assert len(status["jobs"]) == 2
    assert status["daemon"]["heartbeat_at"] == now + timedelta(seconds=5)
    assert (
        next(j for j in status["jobs"] if j["kind"] == "rule")["last_execution"]["finished_at"]
        is None
    )
    repo.scheduler_start("second", jobs[:1], "Europe/Amsterdam", now + timedelta(minutes=1))
    repo.job_finish("first", run, "success", {}, None, now)
    repo.scheduler_heartbeat("first", now + timedelta(days=1))
    status = repo.scheduler_status()
    assert len(status["jobs"]) == 1
    assert status["jobs"][0]["last_execution"]["outcome"] == "interrupted"
    assert status["daemon"]["instance"] == "second"
    assert status["daemon"]["heartbeat_at"] == now + timedelta(minutes=1)
    assert repo.job_watermarks()[("rule", "same")] == now
    run = repo.job_start("second", ("rule", "same"), now, now)
    repo.job_finish("second", run, "warning", {"matches": 2}, "side effect failed", now)
    assert repo.scheduler_status()["jobs"][0]["last_execution"]["summary"] == {"matches": 2}
    repo.scheduler_stop("second", now)
    assert repo.scheduler_status()["daemon"]["stopped_at"] == now


def test_scheduler_upgrade_preserves_data(tmp_path):
    from alembic import command
    from alembic.config import Config

    from excludarr.storage.repo import MIGRATIONS

    url = f"sqlite:///{tmp_path}/db"
    cfg = Config()
    cfg.set_main_option("script_location", MIGRATIONS)
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "0004")
    repo = Repo(url)
    now = datetime.now(UTC)
    repo.queue_add("r", "item", "Example", 10, now)
    repo.cache_set("cache", [1], timedelta(days=1))
    repo.list_publish("movies", [], {}, "unchanged", now)
    repo.history_add("r", "item", "Example", "tag", 0, True, "")
    command.downgrade(cfg, "0004")
    repo = Repo(url)
    repo.scheduler_start("one", [], "UTC", now)
    assert repo.history()[0].title == "Example"
    assert repo.queue_all()[0].item_key == "item"
    assert repo.cache_get("cache") == [1]
    assert repo.list_snapshot("movies").fingerprint == "unchanged"
