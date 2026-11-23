"""T7: Counted once — the listen each repeat and duplicate is of, how far apart, and the read-only checks
(bursts, loops, steady rhythms). Only on make_fixture.py's invented rows."""

import importlib.util
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from traqfreq import counted, history, legacy
from traqfreq.app import create_app
from traqfreq.settings import Settings
from traqfreq.vendor import jimbodj_history

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def checks_db(tmp_path) -> Path:
    spec = importlib.util.spec_from_file_location("make_fixture", ROOT / "scripts/make_fixture.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build(tmp_path / "checks.sqlite", checks=True)


def test_window_sql_vendored_unchanged():
    assert jimbodj_history.window_sql("plex") == "900"
    assert jimbodj_history.window_sql("applemusic") == "(CASE WHEN listens.uri LIKE 'daily:%' THEN 3600 ELSE 300 END)"
    assert jimbodj_history.window_sql("other") == "300"
    assert counted.pair_windows("plex", "lastfm") == [900]
    assert counted.pair_windows("applemusic", "lastfm") == [300, 3600]
    assert counted.pair_windows("spotify", "spotify") == [30]


def test_each_repeat_and_duplicate_has_its_play(legacy_db):
    conn = legacy.connect(legacy_db)
    dup = history.listens(conn, "duplicate")["rows"]
    assert len(dup) == 1
    of = dup[0]["of"]
    # The Plex listen at 20:16 duplicates the Last.fm scrobble at 20:15: 60 s apart, Plex's 15 min window.
    assert of == {"id": 1, "source": "lastfm", "started_at": "2026-11-01T20:15:00Z", "play": True,
                  "gap_s": 60, "window_s": 900}
    rep = history.listens(conn, "repeat")["rows"]
    assert rep[0]["of"]["id"] == 5 and rep[0]["of"]["gap_s"] == 20 and rep[0]["of"]["window_s"] == 30
    assert "of" not in history.listens(conn, "play")["rows"][0]


def test_gaps_add_up_to_the_overview(legacy_db):
    conn = legacy.connect(legacy_db)
    g = counted.gaps(conn)
    o = history.overview(conn)
    assert g["repeats"] == o["not_plays"]["repeat"] and g["duplicates"] == o["not_plays"]["duplicate"]
    for p in g["pairs"]:
        assert sum(b["listens"] for b in p["buckets"]) + p["not_found"] + p["beyond"] == p["listens"]
    plex = next(p for p in g["pairs"] if p["source"] == "plex")
    assert [b for b in plex["buckets"] if b["listens"]] == [{"min": 31, "max": 60, "listens": 1}]
    assert g["pairs"][0]["kind"] == "repeat"  # repeats first


def test_gap_rows_match_their_bucket(checks_db):
    conn = legacy.connect(checks_db)
    g = counted.gaps(conn)
    for p in g["pairs"]:
        for b in p["buckets"]:
            r = history.listens(conn, p["kind"], source=p["source"], of=p["of"], gap=f"{b['min']}-{b['max']}")
            assert r["total"] == b["listens"]
        assert history.listens(conn, p["kind"], source=p["source"], of=p["of"], gap="none")["total"] == p["not_found"]
    # Apple Music's daily summary: an hour's window, so 40 min apart is the same play.
    am = next(p for p in g["pairs"] if p["source"] == "applemusic")
    assert [b["min"] for b in am["buckets"] if b["listens"]] == [901]
    # A flag with no play in its window is shown, not hidden.
    plex = next(p for p in g["pairs"] if p["source"] == "plex")
    assert plex["not_found"] == 1
    orphan = history.listens(conn, "duplicate", source="plex", gap="none")["rows"]
    assert orphan[0]["title"] == "Orphan" and orphan[0]["of"] is None


def test_gap_needs_a_reason(legacy_db):
    with pytest.raises(ValueError):
        history.listens(legacy.connect(legacy_db), "play", gap="0-10")
    with pytest.raises(ValueError):
        history.listens(legacy.connect(legacy_db), "duplicate", gap="soon")


def test_checks_find_burst_loop_rhythm(checks_db):
    c = counted.checks(legacy.connect(checks_db))
    b = c["burst"]
    assert (b["findings"], b["plays"], b["in_bursts"]) == (1, 3, 4)
    assert b["newest"][0]["first"] == "2026-10-10T12:00:00Z" and b["newest"][0]["songs"] == 4
    lp = c["loop"]
    assert (lp["findings"], lp["plays"]) == (1, 10) and lp["newest"][0]["title"] == "Again"
    r = c["rhythm"]
    # The loop is evenly spaced too, but one song isn't a rhythm; the Plex run of 4 songs is.
    assert (r["findings"], r["plays"]) == (1, 12)
    assert r["newest"][0]["gap_s"] == 180 and r["newest"][0]["songs"] == 4


def test_no_findings_in_the_plain_fixture(legacy_db):
    c = counted.checks(legacy.connect(legacy_db))
    assert all(c[k]["findings"] == 0 for k in ("burst", "loop", "rhythm"))
    assert c["plays_checked"] == 6


def test_finding_rows_are_its_plays(checks_db):
    conn = legacy.connect(checks_db)
    c = counted.checks(conn)
    for k in ("burst", "loop", "rhythm"):
        f = c[k]["newest"][0]
        assert history.listens(conn, "play", start=f["start"], end=f["end"])["total"] == f["plays"]


def test_checks_change_no_count(checks_db):
    conn = legacy.connect(checks_db)
    before = history.overview(conn)
    counted.counted(conn)
    after = history.overview(conn)
    assert before["plays"] == after["plays"] and after["adds_up"]
    assert after["plays"] == conn.execute("SELECT COUNT(*) FROM listens WHERE counted = 1").fetchone()[0]


def test_api_counted_cached_and_legacy_untouched(checks_db, tmp_path):
    before = checks_db.read_bytes()
    c = TestClient(create_app(Settings(data_dir=tmp_path / "data", legacy_db=checks_db, port=4492, host="127.0.0.1")))
    a = c.get("/api/history/counted").json()
    assert a["cache"]["hit"] is False and a["checks"]["burst"]["findings"] == 1
    assert c.get("/api/history/counted").json()["cache"]["hit"] is True
    r = c.get("/api/history/listens", params={"status": "duplicate", "of": "lastfm", "gap": "none"}).json()
    assert r["total"] == 1 and "gap IS NULL" in r["rule"]
    assert c.get("/api/history/listens", params={"status": "play", "gap": "0-10"}).status_code == 400
    assert checks_db.read_bytes() == before
    # traqfreq's cache went to its own database, not jimbo-dj's.
    assert sqlite3.connect(tmp_path / "data" / "traqfreq.sqlite").execute(
        "SELECT COUNT(*) FROM stats WHERE name = 'history.counted'").fetchone()[0] == 1
