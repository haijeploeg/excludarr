from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from excludarr.storage.models import Cache, Exception_, History, Queue

MIGRATIONS = str(Path(__file__).parent / "migrations")


@dataclass
class QueueEntry:
    rule: str
    item_key: str
    title: str
    size_bytes: int
    enqueued_at: datetime
    due_at: datetime


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


def _now() -> datetime:
    return datetime.now(UTC)


def _queue(r: Queue) -> QueueEntry:
    return QueueEntry(r.rule, r.item_key, r.title, r.size_bytes, r.enqueued_at, r.due_at)


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
        self, rule: str, item_key: str, title: str, size_bytes: int, due_at: datetime
    ) -> None:
        with Session(self._engine) as s, s.begin():
            s.merge(Queue(rule=rule, item_key=item_key, title=title, size_bytes=size_bytes,
                          enqueued_at=_now(), due_at=due_at))  # fmt: skip

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
    ) -> None:
        with Session(self._engine) as s, s.begin():
            s.add(History(at=_now(), rule=rule, item_key=item_key, title=title, action=action,
                          size_freed=size_freed, ok=ok, detail=detail))  # fmt: skip

    def history(self, limit: int = 100) -> list[HistoryEntry]:
        with Session(self._engine) as s:
            rows = s.scalars(
                select(History).order_by(History.at.desc(), History.id.desc()).limit(limit)
            )
            return [
                HistoryEntry(
                    r.at, r.rule, r.item_key, r.title, r.action, r.size_freed, r.ok, r.detail
                )
                for r in rows
            ]

    def cache_get(self, key: str) -> Any | None:
        with Session(self._engine) as s:
            row = s.get(Cache, key)
            return row.value if row and row.expires_at > _now() else None

    def cache_set(self, key: str, value: Any, ttl: timedelta) -> None:
        with Session(self._engine) as s, s.begin():
            s.merge(Cache(key=key, value=value, expires_at=_now() + ttl))
