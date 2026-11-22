"""T6: the HISTORY overview — top artists under one name, plays per day for the heatmap, and the stats cache
in traqfreq's own database (never jimbo-dj's)."""

import sqlite3
from datetime import date

import pytest
from fastapi.testclient import TestClient

from traqfreq import history, legacy, store
from traqfreq.app import create_app
from traqfreq.settings import Settings

DENVER_DAYS = {"2025-12-31": 1, "2026-11-01": 2, "2026-11-02": 1, "2026-11-03": 1, "2026-11-04": 1}


def _writable_copy(legacy_db, tmp_path):
    copy = tmp_path / "copy.sqlite"
    copy.write_bytes(legacy_db.read_bytes())
    return copy


def test_top_artists_one_name_per_artist(legacy_db):
    o = history.overview(legacy.connect(legacy_db))
    # Spotify's "Paper Lanterns" and the library's "The Paper Lanterns" are one artist, by the library's spelling.
    assert [(a["name"], a["plays"]) for a in o["top_artists"]] == [
        ("Kollektiv Nord", 2), ("The Paper Lanterns", 2), ("Ada Vey", 1), ("Nobody Known", 1)]
    assert o["artists_heard"] == 4
    assert sum(a["plays"] for a in o["top_artists"]) == o["plays"]  # nothing counts twice
    assert o["jimbodj"]["top_artists_match"] is True and o["jimbodj"]["matched_pct_matches"] is True


def test_top_artist_rows_add_up(legacy_db):
    conn = legacy.connect(legacy_db)
    for a in history.overview(conn)["top_artists"]:
        r = history.listens(conn, "play", artist=a["key"])
        assert r["total"] == a["plays"]
    rows = history.listens(conn, "play", artist="paperlanterns")["rows"]
    assert {r["artist"] for r in rows} == {"The Paper Lanterns", "Paper Lanterns"}


def test_days_in_listening_time_zone(legacy_db):
    conn = legacy.connect(legacy_db)
    assert history.summary(conn)["days"] == DENVER_DAYS
    assert history.summary(conn, "UTC")["days"]["2026-01-01"] == 1  # same play, other zone, other day


def test_heatmap_last_year(legacy_db):
    tz = history.listen_tz(legacy.connect(legacy_db))
    h = history.heatmap(DENVER_DAYS, tz, None, date(2026, 11, 22))  # a Sunday
    assert h["first"] == "2025-11-17" and date.fromisoformat(h["first"]).weekday() == 0  # Monday, 53 weeks back
    assert h["last"] == "2026-11-22" and h["days"] == len(h["cells"]) == 53 * 7
    assert h["plays"] == 6 and h["days_played"] == 5
    assert h["busiest"] == {"date": "2026-11-01", "plays": 2}
    assert {c["date"]: c["level"] for c in h["cells"] if c["plays"]}["2026-11-01"] == 4
    assert all(c["level"] == 0 for c in h["cells"] if not c["plays"])
    assert sum(m["plays"] for m in h["months"]) == h["plays"]
    assert h["years"] == [2025, 2026]


def test_heatmap_calendar_year(legacy_db):
    tz = history.listen_tz(legacy.connect(legacy_db))
    h = history.heatmap(DENVER_DAYS, tz, 2025, date(2026, 11, 22))
    assert h["first"] == "2025-01-01" and h["last"] == "2025-12-31" and h["days"] == 365 and h["plays"] == 1
    assert len(h["months"]) == 12
    h = history.heatmap(DENVER_DAYS, tz, 2026, date(2026, 11, 22))
    assert h["last"] == "2026-11-22"  # not past today


def test_levels():
    cuts, levels = history._levels([0, 1, 2, 3, 4, 5, 6, 7, 8])
    assert cuts == [2, 4, 6]
    assert [history.level_of(n, cuts) for n in (0, 1, 2, 3, 4, 5, 6, 7, 8)] == [0, 1, 1, 2, 2, 3, 3, 4, 4]
    assert [(lv["min"], lv["max"]) for lv in levels] == [(0, 0), (1, 2), (3, 4), (5, 6), (7, 8)]
    cuts, levels = history._levels([0, 0])
    assert cuts == [0, 0, 0] and history.level_of(0, cuts) == 0


@pytest.mark.parametrize("period,n", [("2025", 1), ("2026", 5), ("2026-11", 5), ("2026-11-01", 2), ("2025-12-31", 1)])
def test_listens_period(legacy_db, period, n):
    assert history.listens(legacy.connect(legacy_db), "play", period=period)["total"] == n


def test_listens_period_bad(legacy_db):
    for bad in ("26", "2026-13", "2026-02-30", "x"):
        with pytest.raises(ValueError):
            history.listens(legacy.connect(legacy_db), "play", period=bad)


def test_listens_matched(legacy_db):
    conn = legacy.connect(legacy_db)
    no = history.listens(conn, "play", matched=False)
    assert no["total"] == 1 and no["rows"][0]["artist"] == "Nobody Known"
    assert history.listens(conn, "play", matched=True)["total"] == 5


def test_cache_key_follows_jimbodj(legacy_db, tmp_path):
    copy = _writable_copy(legacy_db, tmp_path)
    k1 = history.cache_key(legacy.connect(copy))
    assert k1 == f"v{history.SUMMARY_VERSION}|1793847900.5|3|1793844000|America/Denver"
    assert history.cache_key(legacy.connect(copy), "UTC").endswith("|UTC")  # a new time zone, a new key
    w = sqlite3.connect(copy)  # a scratch copy, never the legacy DB
    w.execute("UPDATE meta SET value = '1793850000.0' WHERE key = 'history_version'")
    w.commit()
    w.close()
    assert history.cache_key(legacy.connect(copy)) != k1


def test_store_builds_once(tmp_path):
    calls = []

    def build():
        calls.append(1)
        return {"n": len(calls)}

    v, info = store.cached(tmp_path, "x", "k1", build)
    assert v == {"n": 1} and info["hit"] is False
    v, info = store.cached(tmp_path, "x", "k1", build)
    assert v == {"n": 1} and info["hit"] is True and len(calls) == 1
    v, info = store.cached(tmp_path, "x", "k2", build)  # new key: rebuilt, the old row goes
    assert v == {"n": 2} and info["hit"] is False
    rows = sqlite3.connect(store.path(tmp_path)).execute("SELECT name, key FROM stats").fetchall()
    assert rows == [("x", "k2")]


def test_api_overview_reads_cache(client, legacy_db, tmp_path):
    before = legacy_db.read_bytes()
    a = client.get("/api/history/overview").json()
    b = client.get("/api/history/overview").json()
    assert a["cache"]["hit"] is False and b["cache"]["hit"] is True
    assert a["plays"] == b["plays"] == 6 and b["top_artists"][0]["name"] == "Kollektiv Nord"
    assert store.path(tmp_path / "data").is_file()  # traqfreq's own database, under TRAQFREQ_DATA_DIR
    assert legacy_db.read_bytes() == before  # jimbo-dj's database is untouched
    assert not (legacy_db.parent / "traqfreq.sqlite").exists()


def test_api_cache_rebuilds_on_new_history_version(legacy_db, tmp_path):
    copy = _writable_copy(legacy_db, tmp_path)
    c = TestClient(create_app(Settings(data_dir=tmp_path / "d", legacy_db=copy, port=4492, host="127.0.0.1")))
    assert c.get("/api/history/overview").json()["plays"] == 6
    w = sqlite3.connect(copy)  # stands in for a jimbo-dj import, on a scratch copy
    w.execute("UPDATE listens SET counted = 0 WHERE id = 9")
    w.execute("UPDATE meta SET value = '1793850000.0' WHERE key = 'history_version'")
    w.commit()
    w.close()
    o = c.get("/api/history/overview").json()
    assert o["cache"]["hit"] is False and o["plays"] == 5


def test_api_heatmap(client):
    h = client.get("/api/history/heatmap", params={"year": 2026}).json()
    assert h["first"] == "2026-01-01" and h["plays"] == 5 and h["timezone"] == "America/Denver"
    assert len(h["levels"]) == 5
    assert client.get("/api/history/heatmap").json()["days"] % 7 in range(7)


def test_api_listens_filters(client):
    r = client.get("/api/history/listens", params={"period": "2026-11-01", "artist": "kollektivnord"}).json()
    assert r["total"] == 1 and r["rows"][0]["source"] == "lastfm"
    assert client.get("/api/history/listens", params={"matched": "false"}).json()["total"] == 1
    assert client.get("/api/history/listens", params={"period": "2026-13"}).status_code == 400
