import sqlite3
from datetime import UTC, datetime

import pytest

from dev.history import build_history
from dev.stack import SetupError


def test_history_uses_actual_keys_user_and_relative_dates(tmp_path):
    schema = {
        "session_history": "CREATE TABLE session_history (id INTEGER PRIMARY KEY AUTOINCREMENT, reference_id INTEGER, started INTEGER, stopped INTEGER, rating_key INTEGER, user_id INTEGER, user TEXT, grandparent_rating_key INTEGER, parent_rating_key INTEGER, media_type TEXT, section_id INTEGER, view_offset INTEGER, live INTEGER, transcode_decision TEXT)",
        "session_history_metadata": "CREATE TABLE session_history_metadata (id INTEGER PRIMARY KEY, rating_key INTEGER, title TEXT, full_title TEXT, media_type TEXT, duration INTEGER, media_index INTEGER, parent_media_index INTEGER)",
        "session_history_media_info": "CREATE TABLE session_history_media_info (id INTEGER PRIMARY KEY, rating_key INTEGER, duration INTEGER, transcode_decision TEXT)",
    }
    state = {
        "schema": schema,
        "user": {"id": 1234, "name": "dev-viewer"},
        "items": [
            {"rating_key": 42, "title": "Recent", "type": "movie", "section": 7, "days": 1},
            {
                "rating_key": 99,
                "title": "Old",
                "type": "episode",
                "section": 8,
                "days": 90,
                "grandparent": 60,
                "parent": 61,
                "season": 2,
                "episode": 1,
            },
        ],
    }
    path = tmp_path / "import.db"
    build_history(path, state, datetime(2026, 11, 11, tzinfo=UTC))
    with sqlite3.connect(path) as db:
        assert db.execute(
            "SELECT rating_key, user_id, user FROM session_history ORDER BY id"
        ).fetchall() == [(42, 1234, "dev-viewer"), (99, 1234, "dev-viewer")]
        assert db.execute("SELECT started FROM session_history ORDER BY id").fetchall() == [
            (1794268800,),
            (1786579200,),
        ]
        assert db.execute(
            "SELECT grandparent_rating_key FROM session_history WHERE rating_key=99"
        ).fetchone() == (60,)
        assert db.execute(
            "SELECT parent_media_index, media_index FROM session_history_metadata WHERE rating_key=99"
        ).fetchone() == (2, 1)


def test_history_refuses_incompatible_schema(tmp_path):
    with pytest.raises(SetupError, match="schema"):
        build_history(
            tmp_path / "import.db", {"schema": {}, "items": [], "user": {}}, datetime.now(UTC)
        )
