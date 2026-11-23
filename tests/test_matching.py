"""T14: matching on snapshots (docs/specs/t13-servers.md): the item shape, the snapshots table, match()."""

import importlib.util
import sqlite3
import unicodedata
from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from test_identity import _scratch
from traqfreq import legacy, matching, snapshots, store
from traqfreq.app import create_app
from traqfreq.settings import Settings

ROOT = Path(__file__).resolve().parents[1]


def _make_fixture():
    spec = importlib.util.spec_from_file_location("make_fixture", ROOT / "scripts/make_fixture.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "data"
    _make_fixture().load_snapshots(d)
    return d


def _snaps():
    jf, nd = _make_fixture().snapshot_answers()
    return (snapshots.from_jellyfin(jf["virtual_folders"], jf["items_pages"], read_at=1.0),
            snapshots.from_navidrome(nd["scan_status"], nd["album_pages"], nd["song_pages"], read_at=1.0))


def _id(n, p):
    return f"{p}{n:031x}"[:32]


# --- the item shape -------------------------------------------------------------------------------------

def test_jellyfin_items():
    jf, _ = _snaps()
    assert (jf["folders"], jf["folder_source"]) == (["/data/music"], "server")  # the books library isn't music
    assert jf["stamp"] == {"items": 14, "newest_created": "2026-11-20T21:00:00.0000000Z"}
    assert len(jf["items"]) == 14  # both pages
    by = {i["id"]: i for i in jf["items"]}
    w = by[_id(101, "a")]
    assert set(w) == set(snapshots.ITEM_FIELDS)
    assert (w["server"], w["file"], w["duration_ms"], w["size"], w["play_count"], w["disc"], w["track"]) == (
        "jellyfin", "Kollektiv Nord/Ringbahn/01 Westkreuz.flac", 312000, 39400000, 4, 1, 1)
    assert w["mb_recording"].endswith("101") and w["mb_release"].endswith("b201")
    book = by[_id(902, "a")]
    assert book["path"].startswith("/data/audiobooks/") and (book["root"], book["file"]) == (None, None)
    ghost = by[_id(110, "a")]
    assert (ghost["path"], ghost["file"], ghost["duration_ms"]) == (None, None, None)
    assert not any(i["hidden"] for i in jf["items"])


def test_navidrome_items():
    _, nd = _snaps()
    assert (nd["folders"], nd["folder_source"]) == (["/music"], "common")  # Subsonic names no folder paths
    assert nd["stamp"] == {"items": 9, "last_scan": "2026-11-23T03:00:00Z", "hidden_paths": 4}
    by = {i["id"]: i for i in nd["items"]}
    h = by[_id(103, "b")]
    assert h["hidden"] and h["file"] is None and h["path"] == "The Paper Lanterns/Low Tide Radio/2-01 - Harbour Lights.flac"
    assert h["mb_release"].endswith("b202")  # from getAlbumList2: Subsonic songs carry only the recording
    assert (h["duration_ms"], h["disc"], h["track"], h["play_count"]) == (221000, 2, 1, 1)
    k = by[_id(111, "b")]
    assert unicodedata.is_normalized("NFD", k["path"]) and k["file"] == unicodedata.normalize("NFC", "Mötley Kru/Über/01 Kreuzberg.flac")
    with pytest.raises(ValueError):
        snapshots.from_navidrome({"subsonic-response": {"status": "failed", "error": {"message": "Wrong username"}}}, [], [])


def test_snapshots_table(tmp_path):
    jf, nd = _snaps()
    d = tmp_path / "data"
    store.save_snapshot(d, jf)
    store.save_snapshot(d, nd)
    store.save_snapshot(d, {**jf, "read_at": 2.0, "items": jf["items"][:3]})  # a new read replaces the old
    got = store.snapshots(d)
    assert set(got) == {"jellyfin", "navidrome"}
    assert (got["jellyfin"]["read_at"], len(got["jellyfin"]["items"])) == (2.0, 3)
    assert got["navidrome"]["items"] == nd["items"] and got["navidrome"]["stamp"] == nd["stamp"]
    assert store.snapshot_stamps(d) == (("jellyfin", 2.0), ("navidrome", 1.0))
    cols = [r[1] for r in sqlite3.connect(store.path(d)).execute("PRAGMA table_info(snapshots)")]
    assert cols == ["server", "read_at", "stamp", "folders", "items"]


# --- the rule -------------------------------------------------------------------------------------------

def _r(id, file=None, rec=None, rel=None, mk="a|t", album="al", disc=1, track=1, dur=200000, path=None):
    return {"id": id, "file": file, "loose": file.casefold() if file else None, "rec": rec, "rel": rel,
            "match_key": mk, "album": album, "disc": disc, "track": track, "duration_ms": dur,
            "path": path or ("ok" if file else "none")}


def test_match_rule():
    m = matching.match([_r(1, "A/x.flac"), _r(2, "A/x.flac"), _r(3, "B/Y.flac"), _r(4, "C/z.flac", mk="c|z")],
                       [_r("i", "A/x.flac"), _r("j", "b/y.flac"), _r("k", "D/q.flac", mk="c|z", dur=201999)])
    got = {p["left"]: (p["right"], p["tier"], p["how"], p["shared"]) for p in m["pairs"]}
    assert got == {1: ("i", "file", "exact", True), 2: ("i", "file", "exact", True),  # one file, two copies
                   3: ("j", "file", "loose", False), 4: ("k", "tags", None, False)}
    assert m["left"] == {} and m["right"] == {}
    # 2 s is the limit; tags need exactly one candidate, and one candidate two copies want is ambiguous
    assert matching.match([_r(1, "Z/1.flac")], [_r("x", dur=202001)])["left"] == {1: "not_on_server"}
    m = matching.match([_r(1), _r(2)], [_r("x")])
    assert (m["pairs"], m["left"], m["right"]) == ([], {1: "ambiguous", 2: "ambiguous"}, {"x": "ambiguous"})
    m = matching.match([_r(1)], [_r("x"), _r("y", dur=199000)])
    assert m["left"] == {1: "ambiguous"} and m["right"] == {"x": "ambiguous", "y": "ambiguous"}
    # a loose key that two items share is ambiguous, and stops there (no tag match after it)
    m = matching.match([_r(1, "A/x.flac")], [_r("x", "a/X.flac"), _r("y", "A/X.FLAC")])
    assert m["left"] == {1: "ambiguous"}
    # one to one: an item matched by file is not offered to the next tier
    m = matching.match([_r(1, "A/x.flac"), _r(2, "Z/2.flac")], [_r("x", "A/x.flac")])
    assert [p["left"] for p in m["pairs"]] == [1] and m["left"] == {2: "not_on_server"}
    # mbid needs recording and release on both sides
    m = matching.match([_r(1, rec="r", rel="l", mk="no|match"), _r(2, rec="r", mk="no|match2")],
                       [_r("x", rec="r", rel="l"), _r("y", rec="r")])
    assert [(p["left"], p["right"], p["tier"]) for p in m["pairs"]] == [(1, "x", "mbid")]
    # reasons, in order
    m = matching.match([_r(1, dur=None), _r(2, path="outside", dur=None), _r(3, "Q/q.flac", dur=None)],
                       [_r("h", path="hidden", dur=None), _r("n", dur=None), _r("o", path="outside", dur=None)])
    assert m["left"] == {1: "no_path", 2: "outside_roots", 3: "hidden_path"}
    assert m["right"] == {"h": "hidden_path", "n": "no_path", "o": "outside_roots"}


# --- the fixture ----------------------------------------------------------------------------------------

def _adds_up(p):
    c = p["counts"]
    left = "copies" if p["left"] == "plex" else "left"
    assert c["matched"] == sum(p["tiers"].values())
    assert c[left] == c["matched"] + c[f"{left}_unmatched"] == c["matched"] + sum(p["unmatched_left"].values())
    assert c["items"] == c["items_matched"] + c["items_unmatched"] == c["items_matched"] + sum(p["unmatched_items"].values())
    assert set(p["rules"]) >= set(c) | set(p["tiers"]) | set(p["notes"])


def test_fixture_matches(legacy_db, data_dir):
    before = legacy_db.read_bytes()
    r = matching.report(legacy.connect(legacy_db), data_dir)
    assert [s["server"] for s in r["snapshots"]] == ["jellyfin", "navidrome"] and r["missing"] == []
    by = {p["pair"]: p for p in r["pairs"]}
    for p in r["pairs"]:
        _adds_up(p)
    jf, nd, jn = by["jellyfin"], by["navidrome"], by["jellyfin-navidrome"]
    assert jf["counts"] == {"copies": 5, "items": 14, "matched": 5, "items_matched": 5, "copies_unmatched": 0,
                            "items_unmatched": 9}
    assert jf["tiers"] == {"file": 5, "mbid": 0, "tags": 0} and jf["notes"] == {"loose": 1, "shared_file": 0, "multi_part": 1}
    assert jf["unmatched_items"] == {"no_path": 1, "outside_roots": 1, "not_in_plex": 6, "multi_part": 1}
    assert nd["tiers"] == {"file": 2, "mbid": 1, "tags": 1} and nd["unmatched_left"] == {"hidden_path": 1}
    assert nd["unmatched_items"] == {"hidden_path": 2, "not_in_plex": 3}
    assert jn["tiers"] == {"plex": 4, "file": 1, "mbid": 1, "tags": 1}
    assert jn["unmatched_left"] == {"no_path": 1, "outside_roots": 1, "ambiguous": 2, "hidden_path": 3}
    assert legacy_db.read_bytes() == before  # read-only


def _plex_side(m, server):
    res = m.result[server]
    out = {p["left"]: p["tier"] for p in res["pairs"]}
    out.update(res["left"])
    return out


def test_problem_cases(legacy_db, data_dir, tmp_path):
    db = _scratch(legacy_db, tmp_path)
    m = matching.matches(legacy.connect(db), data_dir)
    assert _plex_side(m, "jellyfin") == {
        101: "file", 102: "file", 103: "file", 104: "file", 105: "file",
        107: "mbid",              # borrows Navidrome's IDs: its file matched there, Jellyfin's is an .m4a
        108: "file",              # 102's file: both copies point at the one item
        109: "tags",              # outside Plex's folder, so no file key
        110: "no_path", 111: "ambiguous",  # two Jellyfin items with 111's file in other capitals
        112: "not_on_server",     # 105's file in other capitals: its one loose match is 105's already
    }
    assert _plex_side(m, "navidrome") == {
        101: "file", 102: "file", 103: "mbid", 104: "tags", 105: "hidden_path", 107: "file", 108: "file",
        109: "outside_roots", 110: "no_path", 111: "file", 112: "hidden_path",
    }
    jp = {p["left"]: p for p in m.result["jellyfin"]["pairs"]}
    assert jp[103]["how"] == "loose" and jp[102]["shared"] and jp[108]["shared"] and jp[104]["multi_part"]
    assert jp[102]["right"] == jp[108]["right"]
    assert m.result["navidrome"]["pairs"][[p["left"] for p in m.result["navidrome"]["pairs"]].index(103)]["mbid_from"] == "jellyfin"
    assert jp[107]["mbid_from"] == "navidrome"
    assert m.result["jellyfin"]["right"][_id(1042, "a")] == "multi_part"  # 104's second part
    # every tier and every reason turns up in the fixture (here or on the live copies alone)
    base = matching.Matches(m.idn.__class__(legacy.connect(legacy_db)), m.snaps)
    tiers, reasons = set(), set()
    for mm in (m, base):
        for res in mm.result.values():
            tiers |= {p["tier"] for p in res["pairs"]}
            reasons |= set(res["left"].values()) | set(res["right"].values())
    assert tiers == {*matching.TIERS, "plex"}
    assert reasons == set(matching.REASONS)
    # one to one: no item is matched twice, except by copies sharing its file
    for s in ("jellyfin", "navidrome"):
        pairs = m.result[s]["pairs"]
        twice = [k for k, n in Counter(p["right"] for p in pairs).items() if n > 1]
        assert all(p["shared"] for p in pairs if p["right"] in twice)


# --- the API --------------------------------------------------------------------------------------------

def test_api_without_snapshots(client):
    body = client.get("/api/servers/matches").json()
    assert body["pairs"] == [] and body["missing"] == ["jellyfin", "navidrome", "jellyfin-navidrome"]
    assert [s["snapshot"] for s in body["snapshots"]] == [False, False]
    assert set(body["reasons"]) == set(matching.REASONS)
    assert client.get("/api/servers/matches?server=jellyfin").json()["rows"]["total"] == 0


def test_api(legacy_db, tmp_path):
    db = _scratch(legacy_db, tmp_path)
    d = tmp_path / "data"
    s = Settings(data_dir=d, legacy_db=db, port=4492, host="127.0.0.1")
    client = TestClient(create_app(s))
    _make_fixture().load_snapshots(d)
    body = client.get("/api/servers/matches").json()
    assert "rows" not in body
    assert body["snapshots"][1]["hidden_paths"] == 4 and body["snapshots"][0]["folder_source"] == "server"
    for p in body["pairs"]:
        _adds_up(p)
        # every count's rows query, sent as a page would, lists as many rows as its number
        for t, n in p["tiers"].items():
            assert client.get(f"/api/servers/matches?{p['rows'][t]}&limit=200").json()["rows"]["total"] == n
        for r in set(p["unmatched_left"]) | set(p["unmatched_items"]):
            got = client.get(f"/api/servers/matches?{p['rows'][r]}").json()["rows"]
            assert got["total"] == p["unmatched_left"].get(r, 0) + p["unmatched_items"].get(r, 0)
        everything = client.get(f"/api/servers/matches?{p['rows']['all']}").json()["rows"]
        c = p["counts"]
        assert everything["total"] == c["matched"] + sum(p["unmatched_left"].values()) + c["items_unmatched"]
    row = client.get("/api/servers/matches?server=jellyfin&tier=mbid").json()["rows"]["rows"][0]
    assert (row["left"]["rating_key"], row["mbid_from"], row["right"]["id"]) == (107, "navidrome", _id(107, "a"))
    row = client.get("/api/servers/matches?server=navidrome&reason=outside_roots").json()["rows"]["rows"][0]
    assert (row["side"], row["left"]["rating_key"], row["left"]["plex_path"]) == ("left", 109, "/downloads/Ada Vey/Stray.flac")
    all_hidden = client.get("/api/servers/matches?reason=hidden_path").json()["rows"]
    assert {r["pair"] for r in all_hidden["rows"]} == {"navidrome", "jellyfin-navidrome"}
    for bad in ("server=plex", "tier=fuzzy", "reason=nope", "tier=file&reason=ambiguous"):
        assert client.get(f"/api/servers/matches?{bad}").status_code == 400
    page = client.get("/api/servers/matches?server=jellyfin&limit=2&offset=2").json()["rows"]
    assert (page["limit"], page["offset"], len(page["rows"])) == (2, 2, 2)
    # a new snapshot is matched on the next read
    jf, _ = _snaps()
    store.save_snapshot(d, {**jf, "read_at": 5.0, "items": jf["items"][:1]})
    p = client.get("/api/servers/matches").json()["pairs"][0]
    assert (p["counts"]["items"], p["counts"]["matched"]) == (1, 1)


def test_reads_only():
    for mod in ("matching", "snapshots"):
        src = (ROOT / f"src/traqfreq/{mod}.py").read_text(encoding="utf-8")
        assert "httpx" not in src and "urllib.request" not in src and "legacy.connect" not in src
