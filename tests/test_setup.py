"""T4: read-only SETUP API (activity from jimbo-dj's DB, module switches)."""

import sqlite3

from fastapi.testclient import TestClient

from traqfreq import legacy
from traqfreq.app import create_app
from traqfreq.settings import Settings, parse_modules


def test_activity(client, legacy_db):
    before = legacy_db.read_bytes()
    body = client.get("/api/legacy/activity").json()
    assert body["last_scan"] == {"at": "2026-11-05T02:00:00Z", "source": "meta.last_sync"}
    assert body["jobs_source"] == "history_imports"
    assert [j["source"] for j in body["jobs"]] == ["spotify", "plex", "lastfm"]  # newest first
    assert body["jobs"][0] == {
        "id": 3, "kind": "history_import", "source": "spotify", "at": "2026-11-05T03:05:00Z",
        "rows": 0, "added": 0, "note": "file not found",
    }
    assert legacy_db.read_bytes() == before  # read-only


def test_activity_without_tables(tmp_path):
    db = tmp_path / "empty.sqlite"
    sqlite3.connect(db).close()
    conn = legacy.connect(db)
    assert legacy.activity(conn) == {"last_scan": None, "jobs": [], "jobs_source": None}


def test_activity_bad_time(legacy_db, tmp_path):
    copy = tmp_path / "copy.sqlite"
    copy.write_bytes(legacy_db.read_bytes())
    w = sqlite3.connect(copy)  # a scratch copy of the fixture, never the legacy DB
    w.execute("UPDATE meta SET value = 'soon' WHERE key = 'last_sync'")
    w.commit()
    w.close()
    assert legacy.last_scan(legacy.connect(copy)) is None


def test_activity_unconfigured(tmp_path):
    c = TestClient(create_app(Settings(data_dir=tmp_path, legacy_db=None, port=4492, host="127.0.0.1")))
    assert c.get("/api/legacy/activity").status_code == 503
    c = TestClient(create_app(Settings(data_dir=tmp_path, legacy_db=tmp_path / "nope.sqlite", port=4492, host="127.0.0.1")))
    assert c.get("/api/legacy/activity").status_code == 503


def test_modules_default(client):
    mods = client.get("/api/modules").json()["modules"]
    assert [m["id"] for m in mods] == ["L", "H", "T", "D", "M", "F", "S"]
    assert {m["id"] for m in mods if m["on"]} == {"L", "S"}
    assert {m["id"] for m in mods if m["core"]} == {"L", "S"}


def test_modules_switched_on(tmp_path):
    s = Settings.from_env({"TRAQFREQ_MODULES": "history, t ,nope"})
    assert s.modules == frozenset({"L", "S", "H", "T"})
    c = TestClient(create_app(s))
    assert [m["id"] for m in c.get("/api/modules").json()["modules"] if m["on"]] == ["L", "H", "T", "S"]


def test_parse_modules():
    assert parse_modules(None) == frozenset({"L", "S"})
    assert parse_modules("MIXES,F,d") == frozenset({"L", "S", "M", "F", "D"})
