"""T29: traqfreq's library database, the one-time copy and its count check, the reading connection, rollback.
Only against the fixture from scripts/make_fixture.py (invented rows)."""

import hashlib
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from traqfreq import legacy, own
from traqfreq.app import create_app
from traqfreq.settings import Settings

PLEX = own.CUTOVERS["plex"]


def _digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _rw(p):
    c = sqlite3.connect(p)
    c.row_factory = sqlite3.Row
    return c


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "data"


def test_no_copy_reader_is_legacy(legacy_db, data_dir):
    conn = own.reader(legacy_db, data_dir)
    assert not own.path(data_dir).exists()  # reading never creates the file
    assert conn.execute("PRAGMA database_list").fetchall()[-1][1] == "main"
    assert len(conn.execute("PRAGMA database_list").fetchall()) == 1
    assert own.status(data_dir)["cutovers"][0]["state"] == "not_copied"


def test_copy_checks_and_never_writes_legacy(legacy_db, data_dir):
    before = _digest(legacy_db)
    rec = own.copy(legacy_db, data_dir, "plex", "T29 test")
    assert _digest(legacy_db) == before
    assert rec["state"] == own.OWNED and rec["note"] == "T29 test"
    src = _rw(legacy_db)
    for t in PLEX.tables:
        n = src.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        assert rec["check"]["tables"][t] == {"jimbodj": n, "traqfreq": n, "only_jimbodj": 0, "only_traqfreq": 0}
        assert rec["stamp"]["rows"][t] == n
    assert "mb_artist_names" not in rec["check"]["tables"]  # optional, not in the fixture
    # jimbo-dj's numbers, counted its way, plain SQL here
    live = src.execute("SELECT COUNT(*) FROM tracks WHERE removed_at IS NULL").fetchone()[0]
    plays = src.execute("SELECT COUNT(*) FROM listens WHERE counted = 1").fetchone()[0]
    assert rec["check"]["measures"]["tracks"] == {"jimbodj": live, "traqfreq": live}
    assert rec["check"]["measures"]["plays"] == {"jimbodj": plays, "traqfreq": plays}
    assert rec["stamp"]["max_listen_id"] == src.execute("SELECT MAX(id) FROM listens").fetchone()[0]
    assert rec["stamp"]["last_sync"] == src.execute("SELECT value FROM meta WHERE key='last_sync'").fetchone()[0]
    # the copy has jimbo-dj's schema and indexes, and the owned meta keys only
    lib = _rw(own.path(data_dir))
    for t in PLEX.tables:
        assert lib.execute("SELECT sql FROM sqlite_master WHERE name=?", (t,)).fetchone()[0] == \
            src.execute("SELECT sql FROM sqlite_master WHERE name=?", (t,)).fetchone()[0]
    idx = {r[0] for r in lib.execute("SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL")}
    assert {"tracks_artist", "tracks_album", "listens_time", "listens_match", "listens_rk"} <= idx
    keys = {r[0] for r in lib.execute("SELECT key FROM meta")}
    assert keys <= set(PLEX.meta) and "last_sync" in keys
    assert not {"analysis", "features", "saved_playlists"} & {
        r[0] for r in lib.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    log = own.status(data_dir)["log"]
    assert log[0]["action"] == "copied" and log[0]["reason"] == "T29 test"
    assert "rollback plex" in log[0]["detail"]["undo"]


def test_reader_shows_the_copy_and_stays_read_only(legacy_db, data_dir):
    own.copy(legacy_db, data_dir, "plex", "test")
    # traqfreq writes its own copy (as T30's sync will); jimbo-dj's side is left as it was
    lib = _rw(own.path(data_dir))
    lib.execute("UPDATE tracks SET title = 'Copy only' WHERE rating_key = (SELECT MIN(rating_key) FROM tracks)")
    lib.execute("INSERT INTO meta VALUES ('last_sync', '1999999999') "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value")
    lib.commit()
    conn = own.reader(legacy_db, data_dir)
    rk = conn.execute("SELECT MIN(rating_key) FROM tracks").fetchone()[0]
    assert conn.execute("SELECT title FROM tracks WHERE rating_key=?", (rk,)).fetchone()[0] == "Copy only"
    assert conn.execute("SELECT value FROM meta WHERE key='last_sync'").fetchone()[0] == "1999999999"
    # a key no cut-over owns still comes from jimbo-dj
    src = _rw(legacy_db)
    other = src.execute("SELECT key, value FROM meta WHERE key NOT IN (%s) LIMIT 1"
                        % ",".join("?" * len(PLEX.meta)), PLEX.meta).fetchone()
    if other:
        assert conn.execute("SELECT value FROM meta WHERE key=?", (other[0],)).fetchone()[0] == other[1]
    # unowned tables still read jimbo-dj's; existence checks still see every table
    assert conn.execute("SELECT COUNT(*) FROM features").fetchone()[0] == \
        src.execute("SELECT COUNT(*) FROM features").fetchone()[0]
    assert "tracks" in legacy.table_names(conn)
    # jimbo-dj's own copy is unchanged
    assert src.execute("SELECT title FROM tracks WHERE rating_key=?", (rk,)).fetchone()[0] != "Copy only"
    for sql in ("UPDATE tracks SET title='x'", "INSERT INTO meta VALUES ('x','y')", "DELETE FROM main.listens",
                "UPDATE own.tracks SET title='x'", "CREATE TEMP TABLE z (x)"):
        with pytest.raises(sqlite3.OperationalError):
            conn.execute(sql)


def test_api_reads_the_copy(legacy_db, data_dir):
    s = Settings(data_dir=data_dir, legacy_db=legacy_db, port=4492, host="127.0.0.1")
    client = TestClient(create_app(s))
    before = client.get("/api/legacy/summary").json()
    assert client.get("/api/cutovers").json()["cutovers"][0]["state"] == "not_copied"
    own.copy(legacy_db, data_dir, "plex", "test")
    assert client.get("/api/legacy/summary").json()["measures"] == before["measures"]
    lib = _rw(own.path(data_dir))
    lib.execute("UPDATE tracks SET removed_at = 1 WHERE rating_key = (SELECT MIN(rating_key) FROM tracks "
                "WHERE removed_at IS NULL)")
    lib.commit()
    m = {x["id"]: x for x in client.get("/api/legacy/summary").json()["measures"]}
    b = {x["id"]: x for x in before["measures"]}
    assert m["tracks"]["value"] == b["tracks"]["value"] - 1
    st = client.get("/api/cutovers").json()
    assert st["cutovers"][0]["state"] == "owned" and st["log"][0]["action"] == "copied"


def test_second_copy_refused(legacy_db, data_dir):
    own.copy(legacy_db, data_dir, "plex", "first")
    with pytest.raises(own.CutoverError, match="already owned"):
        own.copy(legacy_db, data_dir, "plex", "again")
    assert own.status(data_dir)["log"][0]["action"] == "refused"


def test_mismatch_rolls_back_whole_copy(legacy_db, data_dir, monkeypatch):
    # a check that can't pass: jimbo-dj counts one more track than the copy
    real = own._measure_sql
    monkeypatch.setattr(own, "_measure_sql", lambda sql, t, schema: real(sql, t, schema) + (
        " AND rating_key != (SELECT MIN(rating_key) FROM main.tracks)" if schema == "main" and t == "tracks"
        and "DISTINCT" not in sql else ""))
    with pytest.raises(own.CutoverError, match="doesn't match"):
        own.copy(legacy_db, data_dir, "plex", "test")
    lib = _rw(own.path(data_dir))
    tables = {r[0] for r in lib.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables == {"meta", "cutovers", "cutover_log", "sqlite_sequence"}  # nothing half-copied
    assert lib.execute("SELECT COUNT(*) FROM meta").fetchone()[0] == 0
    assert own.owned(data_dir) == ((), ())
    last = own.status(data_dir)["log"][0]
    assert last["action"] == "refused" and "tracks" in last["detail"]["why"]


def test_missing_required_table_refused(legacy_db, tmp_path, data_dir):
    import shutil
    copy = tmp_path / "copy.sqlite"
    shutil.copy(legacy_db, copy)
    c = sqlite3.connect(copy)
    c.execute("DROP TABLE mb_releases")
    c.commit()
    c.close()
    with pytest.raises(own.CutoverError, match="mb_releases"):
        own.copy(copy, data_dir, "plex", "test")
    assert own.record(data_dir, "plex")["state"] == "not_copied"


def test_reason_and_name_required(legacy_db, data_dir):
    with pytest.raises(own.CutoverError, match="reason"):
        own.copy(legacy_db, data_dir, "plex", " ")
    with pytest.raises(own.CutoverError, match="no cut-over"):
        own.copy(legacy_db, data_dir, "analysis", "not registered until T35")


def test_rollback_puts_aside_and_copy_again(legacy_db, data_dir):
    own.copy(legacy_db, data_dir, "plex", "first")
    lib = _rw(own.path(data_dir))
    lib.execute("UPDATE tracks SET title = 'Written by traqfreq'")
    lib.commit()
    lib.close()
    rec = own.rollback(data_dir, "plex", "test rollback")
    assert rec["state"] == own.ROLLED_BACK
    conn = own.reader(legacy_db, data_dir)
    assert conn.execute("SELECT COUNT(*) FROM tracks WHERE title = 'Written by traqfreq'").fetchone()[0] == 0
    assert len(conn.execute("PRAGMA database_list").fetchall()) == 1  # back to jimbo-dj's copy alone
    lib = _rw(own.path(data_dir))
    aside = [r[0] for r in lib.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'tracks__rolled_back_%'")]
    assert len(aside) == 1  # kept, nothing traqfreq wrote is lost
    assert lib.execute(f'SELECT COUNT(*) FROM "{aside[0]}" WHERE title = \'Written by traqfreq\'').fetchone()[0] > 0
    assert lib.execute("SELECT COUNT(*) FROM meta").fetchone()[0] == 0
    entry = own.status(data_dir)["log"][0]
    assert entry["action"] == "rolled_back" and entry["detail"]["meta"]["last_sync"]
    with pytest.raises(own.CutoverError, match="nothing to roll back"):
        own.rollback(data_dir, "plex", "again")
    again = own.copy(legacy_db, data_dir, "plex", "second")
    assert again["state"] == own.OWNED
    assert own.reader(legacy_db, data_dir).execute(
        "SELECT COUNT(*) FROM tracks WHERE title = 'Written by traqfreq'").fetchone()[0] == 0


def test_command(legacy_db, data_dir, monkeypatch, capsys):
    monkeypatch.setenv("TRAQFREQ_DATA_DIR", str(data_dir))
    monkeypatch.setenv("TRAQFREQ_LEGACY_DB", str(legacy_db))
    assert own.main(["copy", "plex", "--reason", "deploy"]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "owned"
    assert own.main(["copy", "plex", "--reason", "again"]) == 1
    assert "refused" in capsys.readouterr().out
    assert own.main(["status"]) == 0
    assert json.loads(capsys.readouterr().out)["cutovers"][0]["state"] == "owned"
    assert own.main(["rollback", "plex", "--reason", "back"]) == 0


_VOLATILE = {"seconds", "built_at", "hit", "cache", "took", "read_at", "elapsed"}


def _strip(v):
    if isinstance(v, dict):
        return {k: _strip(x) for k, x in v.items() if k not in _VOLATILE}
    if isinstance(v, list):
        return [_strip(x) for x in v]
    return v


def test_every_get_endpoint_answers_the_same_from_the_copy(legacy_db, tmp_path):
    """The reading connection is invisible to every reader: each GET without path parameters answers the same
    before and after the copy (separate data dirs, so no cache is shared)."""
    def client(d):
        return TestClient(create_app(Settings(data_dir=d, legacy_db=legacy_db, port=4492, host="127.0.0.1")))
    a, b = client(tmp_path / "a"), client(tmp_path / "b")
    own.copy(legacy_db, tmp_path / "b", "plex", "test")
    paths = sorted({r.path for r in a.app.routes if "GET" in getattr(r, "methods", set())
                    and r.path.startswith("/api/") and "{" not in r.path and r.path != "/api/cutovers"})
    assert len(paths) > 30
    checked = 0
    for p in paths:
        ra, rb = a.get(p), b.get(p)
        assert ra.status_code == rb.status_code, p
        if ra.status_code == 200 and ra.headers.get("content-type", "").startswith("application/json"):
            assert _strip(ra.json()) == _strip(rb.json()), p
            checked += 1
    assert checked > 30
