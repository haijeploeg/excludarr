"""Native process locks associated with one canonical local SQLite file."""

from contextlib import contextmanager
from pathlib import Path
from urllib.parse import unquote, urlsplit

from filelock import FileLock, SoftFileLock, Timeout
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from excludarr.config import ConfigError


class WorkBusy(ConfigError):
    pass


def sqlite_path(url: str) -> Path | None:
    try:
        parsed = make_url(url)
    except ArgumentError as error:
        raise ConfigError("invalid database URL") from error
    if (
        parsed.get_backend_name() != "sqlite"
        or not parsed.database
        or parsed.database == ":memory:"
    ):
        return None
    database = parsed.database
    if database.startswith("file:") and str(parsed.query.get("uri", "false")).lower() in {
        "true",
        "1",
    }:
        uri = urlsplit(database)
        if parsed.query.get("mode") == "memory" or uri.path == ":memory:":
            return None
        if uri.netloc not in {"", "localhost"}:
            raise ConfigError("SQLite URI must address a local file")
        database = unquote(uri.path)
    return Path(database).resolve()


def require_daemon_database(url: str) -> Path:
    path = sqlite_path(url)
    parsed = make_url(url)
    if (
        path is None
        or (parsed.database or "").startswith("file:")
        or str(parsed.query.get("uri", "false")).lower() in {"true", "1"}
    ):
        raise ConfigError("daemon requires a local file-backed SQLite database")
    return path


@contextmanager
def _lock(path: Path, purpose: str):
    lock = FileLock(str(path) + f".{purpose}.lock")
    if isinstance(lock, SoftFileLock):
        raise ConfigError("this platform has no supported native file lock")
    try:
        lock.acquire(timeout=0)
    except Timeout as error:
        raise WorkBusy(f"another Excludarr {purpose} is active for this database") from error
    except OSError as error:
        raise ConfigError(f"cannot acquire {purpose} lock (OS error {error.errno})") from error
    try:
        yield
    finally:
        lock.release()


@contextmanager
def execution_lock(url: str):
    path = sqlite_path(url)
    if path is None:
        yield
    else:
        with _lock(path, "execution"):
            yield


@contextmanager
def daemon_lock(url: str):
    with _lock(require_daemon_database(url), "daemon"):
        yield
