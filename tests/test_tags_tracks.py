"""T21, TAGS: tracks tagged one by one. Each track's tags by source on their rungs, jimbo-dj's per-track rule
(history._genre_tags, vendored) and the analyzer's styles kept by its strict test (genres.Styles, vendored), the
album page by track, and gate check 2. On the fixture only (scripts/make_fixture.py TAGS, STYLES, FILE_TAGS)."""

import json
import shutil
import sqlite3
from pathlib import Path

from traqfreq import legacy, tags
from traqfreq.vendor import genres, jimbodj_history as jh

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


def test_vendored_unchanged():
    """Styles and _genre_tags are byte for byte jimbo-dj's at 1d8a7cb (checked against a copy when one is beside
    the repo; jimbo-dj is private, so CI checks only that they are there)."""
    assert "Styles" in genres.VENDORED_FROM and hasattr(genres.Styles, "genre_members")
    assert jh._genre_tags.__doc__.startswith("rating_key → the canonical genre tags of the track")
    jimbodj = ROOT.parent / "jimbo-dj"
    if not (jimbodj / ".git").exists():
        return
    import subprocess
    for path, mine, a, b in (("genres.py", genres, "class Styles:", "# Rebuilt in the background"),
                             ("history.py", jh, "def _genre_tags(", "def top(")):
        theirs = subprocess.run(["git", "-C", str(jimbodj), "show", f"1d8a7cb:src/jimbodj/{path}"],
                                capture_output=True, text=True, check=True).stdout
        part = theirs[theirs.index(a):theirs.index(b)].rstrip()
        assert part in Path(mine.__file__).read_text(encoding="utf-8")


def test_styles_strict_test(legacy_db):
    """The strict test on the fixture: kept when the metadata names it or its family; dropped when too weak, of
    another family, or sure from the sound alone with metadata against it."""
    st = genres.get(_conn(legacy_db))
    assert st.sound_genres == {101: ["Rock---Black Metal", "Electronic---Ambient", "Electronic---Dark Ambient"],
                               102: ["Rock---Black Metal"], 103: ["Rock---Doom Metal", "Rock---Shoegaze"]}
    assert st.dropped == {"synth-pop": 1}
    assert genres.get(_conn(legacy_db)) is st  # one per stamp


def test_genre_tags_rule(legacy_db):
    by_track, names = jh._genre_tags(_conn(legacy_db))
    assert by_track == {101: ["atmospheric black metal", "black metal", "metal", "ambient"],
                        102: ["atmospheric black metal", "black metal", "metal"],
                        103: ["death-doom metal", "doom metal"], 104: ["death-doom metal", "doom metal"],
                        105: ["lo-fi hip hop", "soundtrack"]}
    assert names["lo-fi hip hop"] == "Lo-Fi Hip Hop"


def test_track_by_source(legacy_db):
    d = tags.track(_conn(legacy_db), 101)
    s = d["sources"]
    assert [x["name"] for x in s["track"]["tags"]] == ["Ambient", "Black Metal"]
    assert [x["name"] for x in s["file"]["tags"]] == ["Black Metal", "Ambient"] and s["file"]["read"]
    assert [(x["name"], x["rung"]) for x in s["album"]["tags"]] == [("Atmospheric Black Metal", 2), ("Black Metal", 1), ("Metal", 0)]
    assert [x["name"] for x in s["artist"]["tags"]] == ["Black Metal"]
    assert s["mb-release"] == {"tags": [], "found": False}
    snd = {x["discogs"]: (x["score"], x["kept"]) for x in s["sound"]["tags"]}
    assert snd == {"Rock---Black Metal": (0.62, True), "Electronic---Ambient": (0.48, True),
                   "Electronic---Dark Ambient": (0.3, True), "Rock---Punk": (0.2, False)}
    dark = next(x for x in s["sound"]["tags"] if x["name"] == "Dark Ambient")
    assert dark["on_ladder"] is False and dark["rung"] is None and dark["broad"] == "Electronic"
    assert [t["name"] for t in d["tags"]] == ["Atmospheric Black Metal", "Black Metal", "Metal", "Ambient"]
    amb = next(t for t in d["tags"] if t["key"] == "ambient")
    assert amb["rung"] == 1 and amb["broad"] == "Electronic" and not amb["album"]
    assert amb["sources"] == ["track", "file", "sound"]
    assert [t["name"] for t in d["differs"]] == ["Ambient"]
    assert d["check"]["tags"] and d["check"]["styles"]


def test_track_votes_and_files(legacy_db):
    c = _conn(legacy_db)
    d = tags.track(c, 103)
    assert [(x["name"], x["score"]) for x in d["sources"]["mb-release"]["tags"]] == [("Death-Doom Metal", 3), ("Doom Metal", 2)]
    assert [(x["name"], x["score"]) for x in d["sources"]["mb-artist"]["tags"]] == [("Death Metal", 4), ("Post-Punk", 2)]
    assert [x["discogs"] for x in d["styles"]] == ["Rock---Doom Metal", "Rock---Shoegaze"]
    drone = next(x for x in tags.track(c, 104)["sources"]["file"]["tags"] if x["name"] == "Drone")
    assert drone["on_ladder"] is False and drone["broad"] is None
    f = tags.track(c, 105)["sources"]["file"]
    assert f == {"tags": [], "read": False, "error": "unreadable"}
    assert tags.track(c, 105)["sources"]["sound"] == {"tags": [], "analysed": False}


def test_track_not_found(legacy_db):
    c = _conn(legacy_db)
    for key in (106, 999):
        try:
            tags.track(c, key)
        except tags.NotFound:
            continue
        raise AssertionError(key)


def test_album_by_track(legacy_db):
    d = tags.album(_conn(legacy_db), 201)
    assert [t["title"] for t in d["tracks"]] == ["Westkreuz", "Ostkreuz"]
    assert d["differ"] == 1 and [x["name"] for x in d["tracks"][0]["differs"]] == ["Ambient"]
    assert d["tracks"][1]["differs"] == [] and "sources" not in d["tracks"][0]
    assert [t["name"] for t in d["tags"]] == ["Atmospheric Black Metal", "Black Metal", "Metal"]
    speaks = {x["name"]: (x["tracks"], x["files"], x["speaks"], x["album"]) for x in d["from_tracks"]}
    assert speaks == {"Black Metal": (1.0, 1.0, True, True), "Ambient": (0.5, 0.5, True, False),
                      "Atmospheric Black Metal": (0, 0.5, True, True)}
    assert d["check"] == {"tags": 2, "styles": 2, "tracks": 2} and d["track_share"] == 0.5


def test_album_without_tracks_and_unknown(legacy_db):
    c = _conn(legacy_db)
    gone = tags.album(c, 204)  # the removed album: jimbo-dj's tags read it, it has no live tracks
    assert gone["tracks"] == [] and [t["name"] for t in gone["tags"]] == ["Punk"]
    try:
        tags.album(c, 999)
    except tags.NotFound:
        return
    raise AssertionError


def test_track_check(legacy_db):
    d = tags.track_check(_conn(legacy_db))
    assert d["passed"]
    assert {k: d["tags"][k] for k in ("tracks", "with_tags", "ok", "differ")} == {"tracks": 5, "with_tags": 5, "ok": 5, "differ": 0}
    assert {k: d["styles"][k] for k in ("analysed", "kept", "ok", "differ")} == {"analysed": 3, "kept": 3, "ok": 5, "differ": 0}


def test_track_check_sees_a_difference(legacy_db, tmp_path, monkeypatch):
    """If jimbo-dj's rule said something else, the check fails and lists the track with both answers."""
    real = jh._genre_tags

    def other(con):
        by, names = real(con)
        return {**by, 102: ["black metal"]}, names

    monkeypatch.setattr(jh, "_genre_tags", other)
    db = _edit(legacy_db, tmp_path, ("UPDATE meta SET value = '1' WHERE key = 'last_sync'", ()))  # a new stamp
    d = tags.track_check(_conn(db))
    assert not d["passed"] and d["tags"]["differ"] == 1
    assert d["tags"]["items"][0]["rating_key"] == 102 and d["tags"]["items"][0]["jimbodj"] == ["black metal"]


def test_no_file_tags_table(legacy_db, tmp_path):
    db = _edit(legacy_db, tmp_path, ("DROP TABLE file_tags", ()))
    d = tags.track(_conn(db), 101)
    assert d["sources"]["file"]["read"] is False and d["sources"]["file"]["tags"] == []
    assert d["check"]["tags"]


def test_api(client):
    a = client.get("/api/tags/album/201")
    assert a.status_code == 200 and a.json()["differ"] == 1
    t = client.get("/api/tags/track/101").json()
    assert [x["name"] for x in t["differs"]] == ["Ambient"] and "album_tags" in t and "rules" in t
    assert client.get("/api/tags/track/106").status_code == 404
    assert client.get("/api/tags/album/999").status_code == 404
    c = client.get("/api/tags/tracks/check").json()
    assert c["passed"] and c["cache"]["name"] == "tags.tracks"
    assert client.get("/api/tags/tracks/check").json()["cache"]["hit"]
    json.dumps(c)
