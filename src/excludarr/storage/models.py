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


class Cache(Base):
    __tablename__ = "cache"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[object] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
