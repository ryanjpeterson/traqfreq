import sqlite3

import pytest

from traqfreq import legacy


def test_reads(legacy_db):
    conn = legacy.connect(legacy_db)
    assert conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0] == 5


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


def test_summary(legacy_db):
    s = legacy.summary(legacy.connect(legacy_db))
    assert s["counts"] == {"tracks": 5, "albums": 3, "artists": 3, "listens": 6, "track_analysis": 4, "track_tags": 3}
    assert s["missing_tables"] == []
    assert s["times"]["last_plex_sync"] == "2026-11-05T03:00:00Z"
    assert "schema_version" not in s["times"]
