"""T20, TAGS: the ladder on jimbo-dj's vendored tag rules, its agreement with jimbo-dj's families, and its rows.
On the fixture only (invented tags, scripts/make_fixture.py TAGS)."""

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from traqfreq import legacy, tags
from traqfreq.vendor import genres as jd_genres
from traqfreq.vendor import jimbodj_tags as jd

VENDOR = Path(jd.__file__).parent


def _lad(db):
    conn = legacy.connect(db)
    try:
        return tags.overview(conn)
    finally:
        conn.close()


def _edit(db, tmp_path, sql: str, args=()):
    """A scratch copy of the fixture with one change (the fixture itself is never written)."""
    out = tmp_path / "edited.sqlite"
    shutil.copyfile(db, out)
    c = sqlite3.connect(out)
    with c:
        c.execute(sql, args)
    c.close()
    return out


def test_vendored_rules_unchanged():
    rules = json.loads((VENDOR / "tag_rules.json").read_text())
    assert jd.RULES_PATH == VENDOR / "tag_rules.json" and jd.load_rules() == rules
    assert set(rules) == {"_about", "niche_max", "split", "aliases", "rewrites", "junk", "case", "broad"}
    R = jd.Rules(rules)
    assert [p["name"] for p in R.parse("Pop, Rock")] == ["Pop", "Rock"]
    assert R.parse("Hip-Hop")[0]["name"] == "Hip Hop" and R.parse("2010s")[0]["junk"] == "decades"
    assert R.broad("atmospheric black metal") == "Metal" and R.broad("post-punk") == "Rock"
    assert R.broad("synth-pop") == "Electronic" and R.broad("soundtrack") is None
    assert jd_genres.family("pop punk") == "Punk & hardcore" and jd_genres.family("x", "Hip Hop") == "Hip hop"
    assert jd_genres.version() == 0 and jd_genres.get(None).sound_genres == {}


def test_heads():
    assert tags.heads("atmospheric black metal") == {"black metal", "metal"}
    assert tags.heads("death-doom metal") == {"death metal", "doom metal", "metal"}
    assert tags.heads("metal") == set()


def test_ladder_rungs(legacy_db):
    o = _lad(legacy_db)
    n = o["nodes"]
    # Three rungs: Metal, Black Metal, Atmospheric Black Metal.
    assert n["metal"]["rung"] == 0 and n["metal"]["root"]
    assert n["black metal"]["parents"] == ["metal"] and n["black metal"]["rung"] == 1
    assert n["atmospheric black metal"]["parents"] == ["black metal"] and n["atmospheric black metal"]["rung"] == 2
    # Shared parents: Death-Doom Metal sits on two ladders (Death Metal is only an artist's tag, still a rung).
    assert n["death-doom metal"]["parents"] == ["death metal", "doom metal"]
    assert "death-doom metal" in n["death metal"]["children"] and "death-doom metal" in n["doom metal"]["children"]
    # A misspelling counts as its canonical tag; junk is no rung; a tag with no broad tag stands alone.
    assert n["doom metal"]["variants"] == ["Doom Metal", "doom metal"] and n["doom metal"]["albums"] == 1
    assert "2010s" not in n and o["summary"]["junk"] == 1
    assert o["alone"] == ["soundtrack"] and n["soundtrack"]["rung"] is None and n["soundtrack"]["broad"] is None
    # Post-Punk is Rock: Punk is a name inside it under another broad tag, not its parent.
    assert n["post-punk"]["parents"] == ["rock"] and n["post-punk"]["other_heads"] == ["Punk"]
    # Broad tags nobody carries are still roots (Hip Hop: an artist's tag; Electronic: a track's).
    assert not n["electronic"]["in_use"] and n["electronic"]["children"] == ["ambient"]
    assert o["roots"] == ["metal", "hip hop", "punk", "electronic", "rock"]
    assert o["summary"] == {"tags": 12, "roots": 5, "deepest": 2, "shared": 1, "alone": 1, "junk": 1,
                            "albums": 4, "artists": 4}


def test_numbers(legacy_db):
    n = _lad(legacy_db)["nodes"]
    assert (n["metal"]["albums"], n["metal"]["under"], n["metal"]["missing"]) == (1, 2, 1)
    assert (n["hip hop"]["albums"], n["hip hop"]["under"], n["hip hop"]["missing"]) == (0, 1, 1)
    assert n["black metal"]["artists"] == 1 and n["black metal"]["missing"] is None
    assert n["metal"]["below"] == 5  # black, atmospheric black, doom, death, death-doom


def test_agrees_with_jimbodj(legacy_db):
    ch = _lad(legacy_db)["check"]
    assert ch["rules"]["matches"] and [r["key"] for r in ch["rules"]["rows"]] == ["metal", "hip hop", "punk"]
    assert ch["ends"] == {"tags": 8, "ok": 8, "failing": [], "matches": True, "rule": ch["ends"]["rule"]}
    assert ch["stored"]["fresh"] and ch["stored"]["matches"] and ch["passed"]


def test_stored_difference_shows(legacy_db, tmp_path):
    conn = sqlite3.connect(legacy_db)
    v = json.loads(conn.execute("SELECT value FROM stats WHERE name='library.tags'").fetchone()[0])
    conn.close()
    v["families"][0]["missing"] = 0
    db = _edit(legacy_db, tmp_path, "UPDATE stats SET value = ? WHERE name = 'library.tags'", (json.dumps(v),))
    ch = _lad(db)["check"]
    bad = [r for r in ch["stored"]["rows"] if not r["matches"]]
    assert [r["key"] for r in bad] == ["metal"] and bad[0]["ladder"]["missing"] == 1
    assert ch["rules"]["matches"] and not ch["passed"]


def test_stale_stored_row(legacy_db, tmp_path):
    db = _edit(legacy_db, tmp_path, "UPDATE meta SET value = '1793900000' WHERE key = 'last_sync'")
    ch = _lad(db)["check"]
    assert ch["stored"]["fresh"] is False and ch["passed"]


def test_no_stored_row(legacy_db, tmp_path):
    db = _edit(legacy_db, tmp_path, "DELETE FROM stats WHERE name = 'library.tags'")
    ch = _lad(db)["check"]
    assert ch["stored"] is None and ch["passed"]


def test_cache_key_follows_data(legacy_db, tmp_path):
    conn = legacy.connect(legacy_db)
    k1 = tags.cache_key(conn)
    conn.close()
    db = _edit(legacy_db, tmp_path, "UPDATE meta SET value = '1793900000' WHERE key = 'last_sync'")
    conn = legacy.connect(db)
    assert tags.cache_key(conn) != k1 and k1.startswith(f"v{tags.LADDER_VERSION}|")
    conn.close()


def test_rows(legacy_db):
    conn = legacy.connect(legacy_db)
    try:
        carry = tags.albums(conn, "Metal")
        assert [a["title"] for a in carry["items"]] == ["Ringbahn"] and carry["total"] == 1
        under = tags.albums(conn, "metal", "under")
        assert [a["title"] for a in under["items"]] == ["Ringbahn", "Low Tide Radio"]
        miss = tags.albums(conn, "metal", "missing")
        assert miss["total"] == 1 and miss["items"][0]["via"] == ["Death-Doom Metal", "Doom Metal"]
        assert miss["items"][0]["tags"] == ["Death-Doom Metal", "doom metal"] and not miss["items"][0]["carries"]
        assert tags.albums(conn, "Doom Metal")["total"] == 1  # the misspelled "doom metal" counts
        assert tags.artists(conn, "Death Metal")["items"][0]["name"] == "The Paper Lanterns"
        with pytest.raises(ValueError):
            tags.albums(conn, "Black Metal", "missing")
        with pytest.raises(ValueError):
            tags.albums(conn, "metal", "everything")
        with pytest.raises(tags.NotFound):
            tags.albums(conn, "2010s")
    finally:
        conn.close()


def test_api(client):
    r = client.get("/api/tags/ladder")
    assert r.status_code == 200
    d = r.json()
    assert d["check"]["passed"] and d["cache"]["name"] == "tags.ladder" and not d["cache"]["hit"]
    assert client.get("/api/tags/ladder").json()["cache"]["hit"]
    a = client.get("/api/tags/albums", params={"tag": "hip hop", "set": "missing"}).json()
    assert a["total"] == 1 and a["items"][0]["title"] == "Quiet Engines"
    assert client.get("/api/tags/artists", params={"tag": "black metal"}).json()["total"] == 1
    assert client.get("/api/tags/albums", params={"tag": "nothing"}).status_code == 404
    assert client.get("/api/tags/albums", params={"tag": "metal", "set": "x"}).status_code == 400


def test_never_writes(legacy_db, client):
    before = legacy_db.read_bytes()
    client.get("/api/tags/ladder")
    client.get("/api/tags/albums", params={"tag": "metal", "set": "under"})
    assert legacy_db.read_bytes() == before
