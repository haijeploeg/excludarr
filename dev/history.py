"""Generate an import database; the running Tautulli database is read only for schema."""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from dev.stack import SetupError

TABLES = ("session_history", "session_history_metadata", "session_history_media_info")


def build_history(path: Path, state: dict, now: datetime) -> None:
    schema = state["schema"]
    if set(schema) != set(TABLES) or now.tzinfo is None:
        raise SetupError("Unsupported Tautulli fixture schema or naive clock")
    temporary = path.with_suffix(".tmp")
    temporary.unlink(missing_ok=True)
    try:
        with sqlite3.connect(temporary) as db:
            for table in TABLES:
                db.execute(schema[table])
            required = {
                "session_history": {
                    "id",
                    "started",
                    "stopped",
                    "rating_key",
                    "user_id",
                    "user",
                    "view_offset",
                    "section_id",
                    "live",
                    "transcode_decision",
                },
                "session_history_metadata": {"id", "rating_key", "duration", "media_type"},
                "session_history_media_info": {"id", "rating_key", "duration"},
            }
            columns = {
                table: {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
                for table in TABLES
            }
            if any(not required[table] <= columns[table] for table in TABLES):
                raise SetupError("Unsupported Tautulli fixture schema")
            for index, item in enumerate(state["items"], 1):
                started = int((now - timedelta(days=item["days"])).timestamp())
                common = {"id": index, "rating_key": int(item["rating_key"])}
                rows = {
                    "session_history": common
                    | {
                        "reference_id": index,
                        "started": started,
                        "stopped": started + 12,
                        "user_id": int(state["user"]["id"]),
                        "user": state["user"]["name"],
                        "view_offset": 12000,
                        "paused_counter": 0,
                        "media_type": item["type"],
                        "section_id": int(item["section"]),
                        "live": 0,
                        "player": "Excludarr Dev Seed",
                        "platform": "Excludarr Dev",
                        "transcode_decision": "direct play",
                        "grandparent_rating_key": item.get("grandparent"),
                        "parent_rating_key": item.get("parent"),
                    },
                    "session_history_metadata": common
                    | {
                        "title": item["title"],
                        "full_title": item["title"],
                        "duration": 12000,
                        "media_type": item["type"],
                        "live": 0,
                        "parent_media_index": item.get("season"),
                        "media_index": item.get("episode"),
                        "grandparent_rating_key": item.get("grandparent"),
                        "parent_rating_key": item.get("parent"),
                    },
                    "session_history_media_info": common
                    | {
                        "duration": 12000,
                        "transcode_decision": "direct play",
                        "video_decision": "direct play",
                        "audio_decision": "direct play",
                    },
                }
                for table, row in rows.items():
                    row = {key: value for key, value in row.items() if key in columns[table]}
                    db.execute(
                        f"INSERT INTO {table} ({','.join(row)}) VALUES "
                        f"({','.join('?' for _ in row)})",
                        list(row.values()),
                    )
            db.execute("CREATE TABLE version_info (key TEXT, value TEXT)")
            db.execute("INSERT INTO version_info VALUES (?, ?)", ("version", "v2.19.1"))
        temporary.chmod(0o644)
        temporary.replace(path)
    except sqlite3.Error as error:
        raise SetupError("Unsupported Tautulli fixture schema") from error
