from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, delete, func, select, update
from sqlalchemy.orm import Session

from excludarr.jobs import JobKey, JobSpec
from excludarr.storage.models import (
    Cache,
    DaemonState,
    Exception_,
    History,
    JobExecution,
    KnownRatingKey,
    ListSnapshot,
    Queue,
    ScheduledJob,
)

MIGRATIONS = str(Path(__file__).parent / "migrations")


@dataclass
class QueueEntry:
    rule: str
    item_key: str
    title: str
    size_bytes: int
    enqueued_at: datetime
    due_at: datetime
    evidence: list[dict] | None = None


@dataclass
class ExceptionEntry:
    rule: str
    item_key: str
    title: str
    created_at: datetime


@dataclass
class HistoryEntry:
    at: datetime
    rule: str
    item_key: str
    title: str
    action: str
    size_freed: int
    ok: bool
    detail: str
    evidence: list[dict] | None = None
    size_bytes: int | None = None
    side_effect_errors: list[str] | None = None


@dataclass
class CacheEntry:
    key: str
    fetched_at: datetime | None
    expires_at: datetime
    value: Any = None


def _now() -> datetime:
    return datetime.now(UTC)


def _queue(r: Queue) -> QueueEntry:
    return QueueEntry(
        r.rule, r.item_key, r.title, r.size_bytes, r.enqueued_at, r.due_at, r.evidence
    )


@dataclass
class SnapshotEntry:
    slug: str
    payload: list[dict] | None
    report: dict | None
    fingerprint: str | None
    successful_at: datetime | None
    last_attempt_at: datetime
    last_error: str | None


class Repo:
    def __init__(self, url: str) -> None:
        cfg = Config()
        cfg.set_main_option("script_location", MIGRATIONS)
        cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
        command.upgrade(cfg, "head")
        self._engine = create_engine(url)

    def queue_for(self, rule: str) -> dict[str, QueueEntry]:
        with Session(self._engine) as s:
            return {
                r.item_key: _queue(r) for r in s.scalars(select(Queue).where(Queue.rule == rule))
            }

    def queue_all(self) -> list[QueueEntry]:
        with Session(self._engine) as s:
            return [_queue(r) for r in s.scalars(select(Queue).order_by(Queue.due_at))]

    def queue_add(
        self,
        rule: str,
        item_key: str,
        title: str,
        size_bytes: int,
        due_at: datetime,
        *,
        evidence: list[dict] | None = None,
    ) -> None:
        with Session(self._engine) as s, s.begin():
            s.merge(Queue(rule=rule, item_key=item_key, title=title, size_bytes=size_bytes,
                          enqueued_at=_now(), due_at=due_at, evidence=evidence))  # fmt: skip

    def queue_remove(self, rule: str, item_key: str) -> None:
        with Session(self._engine) as s, s.begin():
            s.execute(delete(Queue).where(Queue.rule == rule, Queue.item_key == item_key))

    def exceptions_for(self, rule: str) -> set[str]:
        with Session(self._engine) as s:
            return set(s.scalars(select(Exception_.item_key).where(Exception_.rule == rule)))

    def exceptions_all(self) -> list[ExceptionEntry]:
        with Session(self._engine) as s:
            return [
                ExceptionEntry(r.rule, r.item_key, r.title, r.created_at)
                for r in s.scalars(select(Exception_).order_by(Exception_.created_at))
            ]

    def exception_add(self, rule: str, item_key: str, title: str) -> None:
        with Session(self._engine) as s, s.begin():
            s.merge(Exception_(rule=rule, item_key=item_key, title=title, created_at=_now()))

    def exception_remove(self, rule: str, item_key: str) -> None:
        with Session(self._engine) as s, s.begin():
            s.execute(
                delete(Exception_).where(Exception_.rule == rule, Exception_.item_key == item_key)
            )

    def history_add(
        self,
        rule: str,
        item_key: str,
        title: str,
        action: str,
        size_freed: int,
        ok: bool,
        detail: str,
        *,
        evidence: list[dict] | None = None,
        size_bytes: int | None = None,
        side_effect_errors: list[str] | None = None,
    ) -> None:
        with Session(self._engine) as s, s.begin():
            s.add(History(at=_now(), rule=rule, item_key=item_key, title=title, action=action,
                          size_freed=size_freed, ok=ok, detail=detail, evidence=evidence,
                          size_bytes=size_bytes, side_effect_errors=side_effect_errors))  # fmt: skip

    def history(self, limit: int = 100) -> list[HistoryEntry]:
        with Session(self._engine) as s:
            rows = s.scalars(
                select(History).order_by(History.at.desc(), History.id.desc()).limit(limit)
            )
            return [
                HistoryEntry(
                    r.at,
                    r.rule,
                    r.item_key,
                    r.title,
                    r.action,
                    r.size_freed,
                    r.ok,
                    r.detail,
                    r.evidence,
                    r.size_bytes,
                    r.side_effect_errors,
                )
                for r in rows
            ]

    def cache_entry(self, key: str) -> CacheEntry | None:
        with Session(self._engine) as s:
            row = s.get(Cache, key)
            return CacheEntry(row.key, row.fetched_at, row.expires_at, row.value) if row else None

    def cache_metadata(self) -> list[CacheEntry]:
        with Session(self._engine) as s:
            stmt = select(Cache.key, Cache.fetched_at, Cache.expires_at).order_by(Cache.key)
            return [CacheEntry(*row) for row in s.execute(stmt)]

    def cache_get(self, key: str) -> Any | None:
        row = self.cache_entry(key)
        return row.value if row and row.expires_at > _now() else None

    def cache_set(self, key: str, value: Any, ttl: timedelta) -> None:
        now = _now()
        with Session(self._engine) as s, s.begin():
            s.merge(Cache(key=key, value=value, fetched_at=now, expires_at=now + ttl))

    def rating_keys_record(self, pairs: dict[tuple[str, str], str]) -> None:
        wanted = {(kind, ext, key) for (kind, ext), key in pairs.items()}
        seen = {key for _, _, key in wanted}
        with Session(self._engine) as s, s.begin():
            # Filter in Python: an IN over every library key can exceed SQLite's variable limit.
            stored = {
                (r.kind, r.external_id, r.rating_key)
                for r in s.scalars(select(KnownRatingKey))
                if r.rating_key in seen
            }
            # A rematch keeps the key but changes its external ids: drop the stale rows.
            for kind, ext, key in stored - wanted:
                s.execute(
                    delete(KnownRatingKey).where(
                        KnownRatingKey.kind == kind,
                        KnownRatingKey.external_id == ext,
                        KnownRatingKey.rating_key == key,
                    )
                )
            for kind, ext, key in wanted - stored:
                s.add(
                    KnownRatingKey(kind=kind, external_id=ext, rating_key=key, first_seen_at=_now())
                )

    def rating_keys_for(self, kind: str, external_ids: Iterable[str]) -> set[str]:
        with Session(self._engine) as s:
            stmt = select(KnownRatingKey.rating_key).where(
                KnownRatingKey.kind == kind, KnownRatingKey.external_id.in_(list(external_ids))
            )
            return set(s.scalars(stmt))

    def rating_keys_prune(self, kinds: set[str], keep: set[tuple[str, str]]) -> int:
        with Session(self._engine) as s, s.begin():
            rows = s.scalars(select(KnownRatingKey).where(KnownRatingKey.kind.in_(kinds))).all()
            # Keep a whole key while any of its ids is current: Plex lists ids, such as a
            # movie's tvdb id, that Radarr and Sonarr do not have.
            live = {(r.kind, r.rating_key) for r in rows if (r.kind, r.external_id) in keep}
            gone = [r for r in rows if (r.kind, r.rating_key) not in live]
            for r in gone:
                s.delete(r)
            return len({(r.kind, r.rating_key) for r in gone})

    def list_snapshot(self, slug: str) -> SnapshotEntry | None:
        with Session(self._engine) as session:
            row = session.get(ListSnapshot, slug)
            return (
                SnapshotEntry(
                    **{name: getattr(row, name) for name in SnapshotEntry.__dataclass_fields__}
                )
                if row
                else None
            )

    def list_publish(
        self, slug: str, payload: list[dict], report: dict, fingerprint: str, at: datetime
    ) -> None:
        with Session(self._engine) as session, session.begin():
            session.merge(
                ListSnapshot(
                    slug=slug,
                    payload=payload,
                    report=report,
                    fingerprint=fingerprint,
                    successful_at=at,
                    last_attempt_at=at,
                    last_error=None,
                )
            )

    def list_failure(self, slug: str, error: str, at: datetime) -> None:
        with Session(self._engine) as session, session.begin():
            row = session.get(ListSnapshot, slug)
            if row is None:
                row = ListSnapshot(slug=slug)
                session.add(row)
            row.last_attempt_at = at
            row.last_error = error

    @staticmethod
    def _scheduler_owned(session, instance):
        row = session.get(DaemonState, 1)
        return row is not None and row.instance == instance and row.stopped_at is None

    def scheduler_start(
        self, instance: str, jobs: list[JobSpec], timezone: str, at: datetime
    ) -> None:
        with Session(self._engine) as session, session.begin():
            session.execute(
                update(JobExecution)
                .where(JobExecution.finished_at.is_(None))
                .values(
                    finished_at=at,
                    outcome="interrupted",
                    error="previous daemon stopped before completion",
                )
            )
            session.execute(delete(ScheduledJob))
            session.merge(
                DaemonState(
                    id=1,
                    instance=instance,
                    timezone=timezone,
                    started_at=at,
                    heartbeat_at=at,
                    stopped_at=None,
                )
            )
            for job in jobs:
                session.add(
                    ScheduledJob(
                        kind=job.key[0],
                        name=job.key[1],
                        instance=instance,
                        schedule=job.schedule,
                        state="idle",
                    )
                )

    def scheduler_heartbeat(self, instance: str, at: datetime) -> None:
        with Session(self._engine) as session, session.begin():
            session.execute(
                update(DaemonState)
                .where(
                    DaemonState.id == 1,
                    DaemonState.instance == instance,
                    DaemonState.stopped_at.is_(None),
                )
                .values(heartbeat_at=at)
            )

    def scheduler_stop(self, instance: str, at: datetime) -> None:
        with Session(self._engine) as session, session.begin():
            session.execute(
                update(DaemonState)
                .where(DaemonState.id == 1, DaemonState.instance == instance)
                .values(stopped_at=at)
            )

    def scheduler_update(self, instance: str, jobs: list[dict]) -> None:
        with Session(self._engine) as session, session.begin():
            if not self._scheduler_owned(session, instance):
                return
            for data in jobs:
                row = session.get(ScheduledJob, (data["kind"], data["name"]))
                if row is not None and row.instance == instance:
                    for field in ("next_due", "pending_due", "state", "last_dispatched_due"):
                        setattr(row, field, data[field])

    def job_start(self, instance: str, key: JobKey, due: datetime, at: datetime) -> int:
        with Session(self._engine) as session, session.begin():
            if not self._scheduler_owned(session, instance):
                raise RuntimeError("daemon no longer owns scheduler state")
            row = JobExecution(
                instance=instance, kind=key[0], name=key[1], scheduled_at=due, started_at=at
            )
            session.add(row)
            job = session.get(ScheduledJob, key)
            if job is not None:
                job.state = "running"
                job.last_dispatched_due = max(due, job.last_dispatched_due or due)
            session.flush()
            return row.id

    def job_finish(
        self,
        instance: str,
        run_id: int,
        outcome: str,
        summary: dict,
        error: str | None,
        at: datetime,
    ) -> None:
        with Session(self._engine) as session, session.begin():
            if not self._scheduler_owned(session, instance):
                return
            row = session.get(JobExecution, run_id)
            if row is None or row.instance != instance or row.finished_at is not None:
                return
            row.finished_at, row.outcome, row.summary, row.error = at, outcome, summary, error
            job = session.get(ScheduledJob, (row.kind, row.name))
            if job is not None:
                job.state = "idle"

    def job_watermarks(self) -> dict[JobKey, datetime]:
        with Session(self._engine) as session:
            return {
                (kind, name): due
                for kind, name, due in session.execute(
                    select(
                        JobExecution.kind, JobExecution.name, func.max(JobExecution.scheduled_at)
                    ).group_by(JobExecution.kind, JobExecution.name)
                )
            }

    def scheduler_status(self) -> dict:
        def fields(row):
            return {column.name: getattr(row, column.name) for column in row.__table__.columns}

        with Session(self._engine) as session:
            daemon = session.get(DaemonState, 1)
            jobs = []
            for row in session.scalars(
                select(ScheduledJob).order_by(ScheduledJob.kind, ScheduledJob.name)
            ):
                last = session.scalars(
                    select(JobExecution)
                    .where(JobExecution.kind == row.kind, JobExecution.name == row.name)
                    .order_by(JobExecution.id.desc())
                    .limit(1)
                ).first()
                jobs.append(fields(row) | {"last_execution": fields(last) if last else None})
            return {"daemon": fields(daemon) if daemon else None, "jobs": jobs}
