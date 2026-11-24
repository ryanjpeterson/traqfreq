"""T22, TAGS: the proposals inbox (jimbo-dj's audit and Fix in Plex's preview, vendored; traqfreq's ladder
proposals and rule questions) and gate check 3. On the fixture only (scripts/make_fixture.py TAGS, TAGS_STORED);
cases the fixture doesn't hold go in a scratch copy."""

import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

from traqfreq import legacy, proposals
from traqfreq.vendor import jimbodj_tags as jd
from traqfreq.vendor import tagwrite

ROOT = Path(__file__).resolve().parents[1]


def _conn(db):
    return legacy.connect(db)


def _edit(db, tmp_path, *steps):
    """A scratch copy of the fixture with some changes (the fixture itself is never written)."""
    out = tmp_path / "edited.sqlite"
    shutil.copyfile(db, out)
    c = sqlite3.connect(out)
    with c:
        for sql, args in steps:
            c.execute(sql, args)
    c.close()
    return out


def _stored(db) -> dict:
    c = sqlite3.connect(db)
    v = json.loads(c.execute("SELECT value FROM stats WHERE name = 'library.tags'").fetchone()[0])
    c.close()
    return v


def test_vendored_tagwrite_unchanged():
    """proposal and plan are jimbo-dj's at 1d8a7cb, byte for byte (checked against a copy beside the repo when
    there is one; jimbo-dj is private). Nothing that writes is copied."""
    assert tagwrite.FIXABLE == ["broad", "spelling", "case", "split", "junk"] and tagwrite.DEFAULT == ["broad"]
    for name in ("apply", "undo", "ensure", "_write_file", "_set_local", "_files"):
        assert not hasattr(tagwrite, name)
    jimbodj = ROOT.parent / "jimbo-dj"
    if not (jimbodj / ".git").exists():
        return
    theirs = subprocess.run(["git", "-C", str(jimbodj), "show", "1d8a7cb:src/jimbodj/tagwrite.py"],
                            capture_output=True, text=True, check=True).stdout
    mine = Path(tagwrite.__file__).read_text(encoding="utf-8")
    for a, b in (("# What can be fixed", "\n\n\n_READ_ONLY"), ("def stamp(con):", "def _dedupe("),
                 ("def _dedupe(", "def file_after(")):
        assert theirs[theirs.index(a):theirs.index(b)].rstrip() in mine


def test_proposal_is_fix_in_plex_preview():
    row = {"tags": [{"name": "doom metal"}, {"name": "2010s"}],
           "issues": [{"kind": "case", "op": "rename", "tag": "doom metal", "to": ["Doom Metal"]},
                      {"kind": "junk", "op": "remove", "tag": "2010s"},
                      {"kind": "broad", "op": "add", "tag": "Metal", "because": ["Doom Metal"]}]}
    assert tagwrite.proposal(row, ["broad"]) == (["doom metal", "2010s", "Metal"],
                                                 [{"kind": "broad", "op": "add", "tag": "Metal", "because": ["Doom Metal"]}])
    after, changes = tagwrite.proposal(row, tagwrite.FIXABLE)
    assert after == ["Doom Metal", "Metal"] and [c["kind"] for c in changes] == ["case", "junk", "broad"]
    assert tagwrite.proposal(row, ["niche"]) == (["doom metal", "2010s"], [])


def test_inbox_on_the_fixture(legacy_db):
    d = proposals.inbox(_conn(legacy_db))
    assert d["summary"] == {"albums": 4, "proposed": 3, "issues": 3, "clean": 1, "with_recs": 2, "fixable": 2,
                            "ladder": 1, "rules": 0}
    kinds = {k["kind"]: (k["albums"], k["fixable"]) for k in d["kinds"]}
    assert kinds == {"junk": (1, True), "split": (0, True), "spelling": (0, True), "case": (1, True),
                     "broad": (2, True), "niche": (2, False), "untagged": (0, False)}
    assert [(f["op"], f["tag"], f["albums"]) for f in d["fixes"]] == [
        ("remove", "2010s", 1), ("add", "Hip Hop", 1), ("add", "Metal", 1), ("rename", "doom metal", 1)]
    assert [s["tag"] for s in d["suggestions"]] == ["Ambient", "Death Metal", "Post-Punk", "Drone"]
    # traqfreq's own: Low Tide Radio carries Death-Doom Metal (under Death Metal and Doom Metal) and Doom Metal,
    # not Death Metal. Metal, the broad tag, is jimbo-dj's own fix and isn't repeated.
    assert d["ladder"] == [{"key": "death metal", "tag": "Death Metal", "rung": 1, "albums": 1, "because": ["Death-Doom Metal"]}]
    assert d["rules"] == []
    assert d["fix_in_plex"]["where"] == "jimbo-dj" and d["fix_in_plex"]["until"] == "P6"
    assert {f["kind"]: f["albums"] for f in d["fixable"]} == {"broad": 2, "spelling": 0, "case": 1, "split": 0, "junk": 1}


def test_albums_before_and_after(legacy_db):
    c = _conn(legacy_db)
    every = proposals.albums(c)
    assert [a["title"] for a in every["items"]] == ["Quiet Engines", "Ringbahn", "Low Tide Radio"]  # by artist
    low = every["items"][2]
    assert low["before"] == ["Death-Doom Metal", "doom metal"]
    assert low["after"] == ["Death-Doom Metal", "Doom Metal", "Metal"]
    assert [x["tag"] for x in low["recs"]] == ["Death Metal", "Post-Punk", "Drone"]
    assert low["recs"][0]["artist_votes"] == 4 and low["recs"][0]["sources"] == {"plex-artist": 1, "mb-artist": 4}
    assert low["proposed"] == ["Doom Metal", "Death-Doom Metal", "Metal", "Death Metal", "Post-Punk", "Drone"]
    assert low["ladder"][0]["tag"] == "Death Metal"
    # One fix: the preview uses its kind only.
    metal = next(f for f in proposals.inbox(c)["fixes"] if f["tag"] == "Metal")
    one = proposals.albums(c, "fix", metal["id"])
    assert one["kinds"] == ["broad"] and [a["title"] for a in one["items"]] == ["Low Tide Radio"]
    assert one["items"][0]["after"] == ["Death-Doom Metal", "doom metal", "Metal"]
    # A kind Fix in Plex can't fix (a person decides): before and after the same, no changes.
    niche = proposals.albums(c, "kind", "niche")
    assert niche["kinds"] == [] and [a["title"] for a in niche["items"]] == ["Quiet Engines", "Ringbahn"]
    assert all(a["after"] == a["before"] and a["changes"] == [] for a in niche["items"])
    assert [a["title"] for a in proposals.albums(c, "suggest", "Drone")["items"]] == ["Low Tide Radio"]
    assert [a["title"] for a in proposals.albums(c, "ladder", "death metal")["items"]] == ["Low Tide Radio"]


def test_ladder_proposal_without_its_parent(legacy_db, tmp_path):
    """Atmospheric Black Metal without Black Metal: traqfreq proposes Black Metal (Metal stays jimbo-dj's)."""
    db = _edit(legacy_db, tmp_path, ("UPDATE albums SET genres = ? WHERE album_key = 201",
                                     (json.dumps(["Atmospheric Black Metal"]),)))
    d = proposals.inbox(_conn(db))
    bm = next(g for g in d["ladder"] if g["key"] == "black metal")
    assert bm == {"key": "black metal", "tag": "Black Metal", "rung": 1, "albums": 1, "because": ["Atmospheric Black Metal"]}
    rows = proposals.albums(_conn(db), "ladder", "black metal")["items"]
    assert [a["title"] for a in rows] == ["Ringbahn"]
    assert any(i["kind"] == "broad" and i["tag"] == "Metal" for i in rows[0]["issues"])


def test_rule_question_drill_and_bass(legacy_db, tmp_path):
    """T20's live quirk: "Drill and Bass" is Hip Hop by its "drill" (genres.family); "Bass" has no broad tag."""
    db = _edit(legacy_db, tmp_path, ("UPDATE albums SET genres = ? WHERE album_key = 203",
                                     (json.dumps(["Drill and Bass"]),)))
    d = proposals.inbox(_conn(db))
    assert d["rules"] == [{"key": "drill and bass", "tag": "Drill and Bass", "broad": "Hip Hop", "family": "Hip hop",
                           "match": "drill", "last": "Bass", "albums": 1, "artists": 0}]
    rows = proposals.albums(_conn(db), "rule", "Drill and Bass")
    assert rows["question"]["match"] == "drill" and [a["title"] for a in rows["items"]] == ["Quiet Engines"]
    # Post-Punk (its head Punk has a broad tag) and Lo-Fi Hip Hop (matched at its end) aren't questions.
    assert proposals.rule_questions(jd.Library(_conn(legacy_db)), _lad(legacy_db)) == []


def _lad(db):
    from traqfreq import tags
    return tags.ladder(tags.library(_conn(db)))


def test_check_passes_and_fails(legacy_db, tmp_path):
    c = proposals.inbox(_conn(legacy_db))["check"]
    assert c["passed"] and c["matches"] and c["fresh"]
    assert c["tags"]["tags"] == 13 and c["tags"]["ok"] == 13
    assert c["issues"]["ok"] == 7 and c["fixes"]["ok"] == 4 and c["suggestions"]["ok"] == 4
    # jimbo-dj stored something else, fresh: not passed, and the row shows both answers.
    v = _stored(legacy_db)
    v["tags"][0]["tracks"] = 3
    v["summary"]["issues"]["broad"] = 3
    v["fixes"] = v["fixes"][:3]
    db = _edit(legacy_db, tmp_path, ("UPDATE stats SET value = ? WHERE name = 'library.tags'", (json.dumps(v),)))
    c = proposals.inbox(_conn(db))["check"]
    assert not c["passed"] and c["fresh"]
    assert c["tags"]["differ"] == 1 and c["tags"]["differing"][0]["jimbodj"]["tracks"] == 3
    assert c["tags"]["differing"][0]["traqfreq"]["tracks"] == 2
    assert not c["issues"]["matches"] and c["fixes"]["differ"] == 1 and c["suggestions"]["matches"]
    # The same row, stale (built before the last sync): passes, and says it's stale.
    stale = json.dumps([1, 1, "1", 7, 1795000000.0, None, None])
    db2 = tmp_path / "stale.sqlite"
    shutil.copyfile(db, db2)
    with sqlite3.connect(db2) as w:
        w.execute("UPDATE stats SET stamp = ? WHERE name = 'library.tags'", (stale,))
    c = proposals.inbox(_conn(db2))["check"]
    assert c["passed"] and not c["fresh"] and not c["matches"]


def test_check_without_stored_row(legacy_db, tmp_path):
    db = _edit(legacy_db, tmp_path, ("DELETE FROM stats WHERE name = 'library.tags'", ()))
    c = proposals.inbox(_conn(db))["check"]
    assert c["stored"] is None and not c["passed"]


def test_api(client):
    r = client.get("/api/tags/proposals")
    assert r.status_code == 200 and r.json()["check"]["passed"] and not r.json()["cache"]["hit"]
    assert client.get("/api/tags/proposals").json()["cache"]["hit"]
    a = client.get("/api/tags/proposals/albums", params={"group": "kind", "value": "broad"}).json()
    assert a["total"] == 2 and a["kinds"] == ["broad"]
    assert client.get("/api/tags/proposals/albums", params={"group": "x"}).status_code == 400
    assert client.get("/api/tags/proposals/albums", params={"group": "kind"}).status_code == 400
    assert client.get("/api/tags/proposals/albums", params={"group": "fix", "value": "nope"}).status_code == 404
    assert client.get("/api/tags/proposals/albums", params={"group": "ladder", "value": "metal"}).status_code == 404
    # Nothing to accept: no route writes.
    for method in ("post", "put", "patch", "delete"):
        assert getattr(client, method)("/api/tags/proposals").status_code == 405


def test_never_writes(legacy_db, client):
    before = legacy_db.read_bytes()
    client.get("/api/tags/proposals")
    client.get("/api/tags/proposals/albums")
    assert legacy_db.read_bytes() == before
