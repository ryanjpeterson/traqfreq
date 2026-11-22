import sqlite3

import pytest

from traqfreq import legacy


def test_reads(legacy_db):
    conn = legacy.connect(legacy_db)
    assert conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0] == 6  # raw rows, one removed


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO meta VALUES ('x', 'y')",
        "UPDATE tracks SET title = 'nope'",
        "DELETE FROM listens",
        "CREATE TABLE evil (id INTEGER)",
        "DROP TABLE tracks",
    ],
)
def test_write_raises(legacy_db, sql):
    before = legacy_db.read_bytes()
    conn = legacy.connect(legacy_db)
    with pytest.raises(sqlite3.OperationalError, match="readonly|read-only|query_only|attempt to write"):
        conn.execute(sql)
        conn.commit()
    conn.close()
    assert legacy_db.read_bytes() == before


def test_missing_file(tmp_path):
    with pytest.raises(legacy.LegacyDBMissing):
        legacy.connect(tmp_path / "nope.sqlite")
    assert not (tmp_path / "nope.sqlite").exists()


def test_summary_raw_rows(legacy_db):
    s = legacy.summary(legacy.connect(legacy_db))
    assert s["counts"] == {"tracks": 6, "albums": 4, "artists": 4, "analysis": 4, "features": 3, "listens": 9,
                           "listen_matches": 6, "history_imports": 3}
    assert s["missing_tables"] == []
    assert s["times"] == {"last_sync": "1793844000"}
    assert "history_version" not in s["times"]


def test_summary_counts_like_jimbodj(legacy_db):
    """jimbo-dj's definitions (library.py stats, history.py counted): live tracks, distinct album_key and
    artist_key of live tracks, counted listens. The removed track and the three non-plays don't count."""
    m = {x["id"]: x for x in legacy.summary(legacy.connect(legacy_db))["measures"]}
    assert [x for x in m] == ["tracks", "albums", "artists", "plays"]
    assert {k: v["value"] for k, v in m.items()} == {"tracks": 5, "albums": 3, "artists": 3, "plays": 6}
    assert m["tracks"]["rule"] == "SELECT COUNT(*) FROM tracks WHERE removed_at IS NULL"
    assert m["albums"]["rule"] == "SELECT COUNT(DISTINCT album_key) FROM tracks WHERE removed_at IS NULL"
    assert m["plays"]["rule"] == "SELECT COUNT(*) FROM listens WHERE counted = 1"
    assert all(v["matches"] is True for v in m.values())
    assert m["tracks"]["jimbodj"] == {"value": 5, "built_at": "2026-11-05T02:01:00Z", "source": "stats.library.stats"}
    assert m["plays"]["jimbodj"]["source"] == "stats.history.overview"


def test_measures_disagree_and_missing(legacy_db, tmp_path):
    copy = tmp_path / "copy.sqlite"
    copy.write_bytes(legacy_db.read_bytes())
    w = sqlite3.connect(copy)  # a scratch copy of the fixture, never the legacy DB
    w.execute("UPDATE tracks SET removed_at = 1 WHERE rating_key = 105")
    w.execute("DELETE FROM stats WHERE name = 'history.overview'")
    w.commit()
    w.close()
    m = {x["id"]: x for x in legacy.measures(legacy.connect(copy))}
    assert m["tracks"]["value"] == 4 and m["tracks"]["matches"] is False
    assert m["plays"]["jimbodj"] is None and m["plays"]["matches"] is None


def test_measures_without_tables(tmp_path):
    db = tmp_path / "empty.sqlite"
    sqlite3.connect(db).close()
    s = legacy.summary(legacy.connect(db))
    assert s["measures"] == [] and s["counts"] == {}
