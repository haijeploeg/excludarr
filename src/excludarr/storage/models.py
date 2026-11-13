from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, Integer, String, Text
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import DateTime, TypeDecorator


class UTCDateTime(TypeDecorator):
    """Stores aware datetimes as UTC; returns aware UTC (SQLite drops tzinfo)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime not allowed; use timezone-aware UTC")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Base(DeclarativeBase):
    pass


class Queue(Base):
    __tablename__ = "queue"
    rule: Mapped[str] = mapped_column(String, primary_key=True)
    item_key: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String)
    size_bytes: Mapped[int] = mapped_column(Integer)
    enqueued_at: Mapped[datetime] = mapped_column(UTCDateTime)
    due_at: Mapped[datetime] = mapped_column(UTCDateTime)
    evidence: Mapped[list[dict] | None] = mapped_column(JSON)


class Exception_(Base):
    __tablename__ = "exception"
    rule: Mapped[str] = mapped_column(String, primary_key=True)
    item_key: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class History(Base):
    __tablename__ = "history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime)
    rule: Mapped[str] = mapped_column(String)
    item_key: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    size_freed: Mapped[int] = mapped_column(Integer)
    ok: Mapped[bool] = mapped_column(Boolean)
    detail: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list[dict] | None] = mapped_column(JSON)
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    side_effect_errors: Mapped[list[str] | None] = mapped_column(JSON)


class Cache(Base):
    __tablename__ = "cache"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[object] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    fetched_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class ListSnapshot(Base):
    __tablename__ = "list_snapshot"
    slug: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(String)
    successful_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_attempt_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_error: Mapped[str | None] = mapped_column(Text)


class KnownRatingKey(Base):
    __tablename__ = "known_rating_key"
    kind: Mapped[str] = mapped_column(String, primary_key=True)  # "movie" | "show"
    external_id: Mapped[str] = mapped_column(String, primary_key=True)  # "tmdb://19933"
    rating_key: Mapped[str] = mapped_column(String, primary_key=True)
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)


class DaemonState(Base):
    __tablename__ = "daemon_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instance: Mapped[str] = mapped_column(String)
    timezone: Mapped[str] = mapped_column(String)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime)
    heartbeat_at: Mapped[datetime] = mapped_column(UTCDateTime)
    stopped_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class ScheduledJob(Base):
    __tablename__ = "scheduled_job"
    kind: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, primary_key=True)
    instance: Mapped[str] = mapped_column(String)
    schedule: Mapped[str] = mapped_column(String)
    state: Mapped[str] = mapped_column(String)
    next_due: Mapped[datetime | None] = mapped_column(UTCDateTime)
    pending_due: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_dispatched_due: Mapped[datetime | None] = mapped_column(UTCDateTime)


class JobExecution(Base):
    __tablename__ = "job_execution"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instance: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    scheduled_at: Mapped[datetime] = mapped_column(UTCDateTime)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    outcome: Mapped[str | None] = mapped_column(String)
    error: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[dict | None] = mapped_column(JSON)
