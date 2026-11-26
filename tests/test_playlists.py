"""T24: PLAYLISTS, the Junction's lines (P5), on the fixture's invented saved playlists. Every count is worked out
here the plain way (or through the vendored Styles, already checked against jimbo-dj in test_tags_tracks.py)."""
import hashlib
import shutil
import sqlite3
import subprocess
from pathlib import Path

from traqfreq import legacy
from traqfreq.vendor import genres, rules

ROOT = Path(__file__).resolve().parents[1]
LIVE = {101, 102, 103, 104, 105}


def _style(db, name):
    st = genres.get(legacy.connect(db))
    return {k for k, sc in st.scores.items() if sc.get(name, 0) >= genres.MATCH} & LIVE


def test_vendored_unchanged():
    """The rules engine and the read-only parts of store, make, clusters, playlists, browse and history are
    jimbo-dj's at 1d8a7cb (checked against a copy beside the repo; CI checks only that they are there)."""
    assert "Matching" in rules.VENDORED_FROM and hasattr(rules, "branch_sets")
    jimbodj = ROOT.parent / "jimbo-dj"
    if not (jimbodj / ".git").exists():
        return
    vendor = ROOT / "src/traqfreq/vendor"
    for path, mine, a, b in (("rules.py", "rules.py", "SOUND = (", "# --- Picking"),
                             ("store.py", "store.py", "def _row(", "def save("),
                             ("make.py", "make.py", "def spec_of(", "def link_of("),
                             ("make.py", "make.py", "def clean(", "# --- Candidates"),
                             ("clusters.py", "clusters.py", "def current_run_id(", "def list_clusters("),
                             ("playlists.py", "playlists.py", "def base_name(", "def legacy_title("),
                             ("browse.py", "browse.py", "def _where(", "def _filter_keys("),
                             ("history.py", "history.py", "def listened_keys(", "def band_share("),
                             ("insights.py", "jimbodj_insights.py", "def track_family(", "def genre_view("),
                             ("facets.py", "facets.py", 'kind, _, ident = ref.partition(":")\n    if kind == "cluster"',
                              '    if kind in ("artist", "album"):')):
        theirs = subprocess.run(["git", "-C", str(jimbodj), "show", f"1d8a7cb:src/jimbodj/{path}"],
                                capture_output=True, text=True, check=True).stdout
        part = theirs[theirs.index(a):theirs.index(b)].rstrip()
        assert part in (vendor / mine).read_text(encoding="utf-8"), path


def test_listing(client):
    r = client.get("/api/playlists").json()
    assert (r["count"], r["with_lines"], r["stale"]) == (10, 4, 1)
    assert r["on"] == {"plex": 3, "jellyfin": 0, "navidrome": 0}
    kinds = [(k["kind"], k["count"]) for k in r["kinds"]]
    assert kinds == [("explore", 3), ("blend", 1), ("mix", 1), ("cluster", 2), ("like", 1), ("history", 1), ("setlist", 1)]
    rows = {x["id"]: x for k in r["kinds"] for x in k["rows"]}
    assert rows[1]["slug"] == "night-lines" and rows[1]["name"] == "Night lines" and rows[1]["lines"] == 3
    assert rows[2]["made_by"] == "rules" and rows[2]["lines"] == 2  # a genre blend reads as a tree
    assert rows[3]["made_by"] == "rules" and rows[3]["lines"] == 1  # an old Explore filter: one line
    assert rows[4]["made_by"] == "mix" and rows[4]["lines"] == 0
    assert rows[8]["made_by"] == "period" and rows[8]["lines"] == 0  # a history playlist: no tree
    assert rows[6]["stale"] is True and rows[6]["stale_in_plex"] == 1


def test_three_switches(client):
    """Ryan's three switches, read-only: Plex is jimbo-dj's in_plex; Jellyfin and Navidrome off until P6."""
    rows = {x["id"]: x for k in client.get("/api/playlists").json()["kinds"] for x in k["rows"]}
    for x in rows.values():
        assert [s["server"] for s in x["switches"]] == ["plex", "jellyfin", "navidrome"]
        assert all(not s["on"] and s["from"] == "P6" for s in x["switches"][1:])
    assert {i for i, x in rows.items() if x["switches"][0]["on"]} == {1, 4, 7}
    assert rows[7]["switches"][0]["error"] == "Plex didn't answer"
    assert rows[1]["switches"][0]["plex_key"] == 9001


def test_lines_and_conditions(client):
    """Night lines: AND with NOT, OR, and a nested OR inside AND; each condition with its own count."""
    j = client.get("/api/playlists/night-lines").json()
    L = j["lines"]
    a, b, c = L["lines"]
    # 2010s = Ringbahn (101, 102); sad = 101 (analysed at version 2; 102's analysis is version 1).
    assert (a["count"], a["share"], a["label"]) == (1, 8, "Ringbahn, not sad")
    assert [(x["f"], x["count"]) for x in a["match"]["all"]] == [("decade", 2)]
    assert [(x["f"], x["count"]) for x in a["match"]["not"]] == [("mood", 1)]
    # Ada Vey = 105; played in 2025 = 102 (2026-01-01 05:30 UTC is 2025 in America/Denver).
    any_ = b["match"]["all"][0]
    assert any_["type"] == "group" and [(x["v"], x["count"]) for x in any_["any"]] == [("Ada Vey", 1), ("2025", 1)]
    assert b["count"] == 2 and b["words"] == "(Ada Vey or played in 2025)"
    # happy = 101, 103; 100-110 BPM = 103 (104 BPM); 8A = 101.
    assert c["count"] == 2 and c["words"] == "happy · (100-110 BPM or 8A)"
    assert L["total"] == 4 and L["library"] == 5 and L["n"] == 20
    assert j["stored"]["count"] == 4 and [x["rating_key"] for x in j["stored"]["rows"]] == [101, 103, 102, 105]


def test_counts_equal_branch_sets(client, legacy_db):
    """Every line's count is jimbo-dj's rules.branch_sets on the same tree, and the total its union."""
    from traqfreq.vendor import jimbodj_history as jh
    from traqfreq.vendor import jimbodj_insights as ji
    from zoneinfo import ZoneInfo
    conn = legacy.connect(legacy_db)
    for ref in ("night-lines", "blend-black-metal-doom-metal", "from-the-2020s", "inside-the-lines"):
        j = client.get(f"/api/playlists/{ref}").json()
        assert j["lines_error"] is None, ref
        with jh.in_zone(ZoneInfo("America/Denver")), ji.in_tz(ZoneInfo("America/Denver")):
            sets = rules.branch_sets(conn, rules.clean(j["tree"]))
        assert [x["count"] for x in j["lines"]["lines"]] == [len(s) for s in sets], ref
        assert j["lines"]["total"] == len(set().union(*sets)), ref


def test_blend_and_filter(client, legacy_db):
    j = client.get("/api/playlists/2").json()["lines"]
    assert [(x["share"], x["words"]) for x in j["lines"]] == [(12, "black metal"), (8, "doom metal")]  # 60:40 of 20
    assert [x["count"] for x in j["lines"]] == [len(_style(legacy_db, "black metal")), len(_style(legacy_db, "doom metal"))]
    f = client.get("/api/playlists/from-the-2020s").json()["lines"]
    assert [(x["words"], x["count"]) for x in f["lines"]] == [("2020s", 3)]  # 103, 104 (2021), 105 (2023)


def test_in_scopes(client):
    """in:saved (its stored tracks), in:cluster (the current run's members), in:mix (the newest mix, analysed)."""
    a, b = client.get("/api/playlists/inside-the-lines").json()["lines"]["lines"]
    assert [x["count"] for x in a["match"]["all"]] == [3]  # From the 2020s: 103, 104, 105
    assert [x["count"] for x in a["match"]["not"]] == [2]  # Quiet Engines: 103, 105
    assert a["count"] == 1
    assert b["count"] == 2  # the daily mix 101, 103, 104; 104 isn't analysed


def test_rows_behind_counts(client):
    r = client.get("/api/playlists/night-lines/rows", params={"line": "c", "path": "all.1"}).json()
    assert r["count"] == 2 and [x["rating_key"] for x in r["rows"]] == [101, 103] and r["words"] == "100-110 BPM or 8A"
    r = client.get("/api/playlists/night-lines/rows", params={"line": "a"}).json()
    assert [x["rating_key"] for x in r["rows"]] == [102]
    assert client.get("/api/playlists/night-lines/rows", params={"line": "z"}).status_code == 404
    assert client.get("/api/playlists/night-lines/rows", params={"line": "a", "path": "all.9"}).status_code == 400
    assert client.get("/api/playlists/daily-mix/rows", params={"line": "a"}).status_code == 404
    assert client.get("/api/playlists/no-such-list").status_code == 404


def test_url_tree(client):
    """Any tree in jimbo-dj's URL form, read the same way (nothing saved)."""
    q = "b=mood:happy,!style:black%20metal~10&b=(artist:Ada%20Vey|decade:2010s)~10&n=10"
    j = client.get(f"/api/playlists/lines?{q}").json()
    assert [x["count"] for x in j["lines"]] == [1, 3] and j["total"] == 4
    assert j["query"].startswith("b=mood:happy,!style:black+metal~5")
    r = client.get(f"/api/playlists/lines/rows?{q}&line=b").json()
    assert [x["rating_key"] for x in r["rows"]] == [101, 102, 105]
    assert client.get("/api/playlists/lines?b=nope:1~5").status_code == 400
    assert client.get("/api/playlists/lines?b=bpm:fast~5").status_code == 400


def test_removed_tracks_shown_not_counted(client):
    """A stale cluster's stored track that is no longer in the library: listed, marked, not live."""
    j = client.get("/api/playlists/gone-grey").json()
    assert j["stored"]["count"] == 1 and j["stored"]["live"] == 0 and j["stored"]["rows"][0]["live"] is False


def test_reads_only(client, legacy_db):
    before = hashlib.sha256(legacy_db.read_bytes()).hexdigest()
    for path in ("/api/playlists", "/api/playlists/night-lines", "/api/playlists/inside-the-lines",
                 "/api/playlists/lines?b=decade:2010s~5"):
        assert client.get(path).status_code == 200
    assert hashlib.sha256(legacy_db.read_bytes()).hexdigest() == before


def test_no_saved_table(tmp_path, legacy_db):
    from fastapi.testclient import TestClient
    from traqfreq.app import create_app
    from traqfreq.settings import Settings
    db = tmp_path / "old.sqlite"
    shutil.copy(legacy_db, db)
    c = sqlite3.connect(db)
    c.execute("DROP TABLE saved_playlists")
    c.commit()
    c.close()
    client = TestClient(create_app(Settings(data_dir=tmp_path / "d", legacy_db=db, port=4492, host="127.0.0.1")))
    assert client.get("/api/playlists").status_code == 404
