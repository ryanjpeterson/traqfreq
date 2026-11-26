"""T26: movements, rooted to roaming (docs/specs/t24-playlists.md). New in traqfreq, a preview only, not part of
the gate. Fixture only (invented rows).

The fixture's tags (TAGS' ladder, T20) and style scores (vendor/genres.py Styles, a track counts as a style at 0.45):
- Doom Metal (rung 1 under Metal) has Death-Doom Metal under it; Death-Doom Metal's other parent is Death Metal.
- Black Metal (rung 1) has Atmospheric Black Metal under it.
- movements.json: Doom and drone names Doom Metal (and Sludge Metal, Drone Metal, Stoner Rock, Drone, Dark Ambient);
  Blackgaze names Atmospheric Black Metal (and Blackgaze, Post-Black Metal, Shoegaze, Post-Rock, Dream Pop).
- Scores: doom metal 103, 104; death-doom metal 103, 104; death metal 103, 104; dark ambient 101 (0.48);
  drone 103 (0.16, under 0.45); shoegaze 103 (0.4, under); black metal 101, 102; atmospheric black metal 101, 102.
"""

from traqfreq import junction, legacy, playlists, reach
from traqfreq.vendor import rules

DOOM = "b=style:doom metal~10&n=20"


def _counts(line):
    return [(s["stop"], s["count"], s["added"]) for s in line["stops"]]


def test_doom_metal_by_hand(legacy_db):
    """Rooted {103, 104}; ladder adds Death-Doom Metal (the same two); movement adds Doom and drone's tags, and
    Dark Ambient brings 101; roaming adds Death Metal, Death-Doom Metal's other parent (103, 104 again)."""
    r = reach.reach_from_query(legacy.connect(legacy_db), DOOM)
    line = r["lines"][0]
    assert [(f["key"], f["path"], [m["id"] for m in f["movements"]]) for f in line["follows"]] == [
        ("doom metal", "all.0", ["doom-drone"])]
    assert _counts(line) == [("rooted", 2, 0), ("ladder", 2, 0), ("movement", 3, 1), ("roaming", 3, 1)]
    new = {s["stop"]: [(x["key"], x["via"]) for x in s["new_tags"]] for s in line["stops"]}
    assert new["rooted"] == [("doom metal", "tag")]
    assert new["ladder"] == [("death-doom metal", "ladder")]
    assert [k for k, _ in new["movement"]] == ["sludge metal", "drone metal", "stoner rock", "drone", "dark ambient"]
    assert new["roaming"] == [("death metal", "neighbour")]
    assert line["stops"][3]["new_tags"][0]["of"] == "Death-Doom Metal"
    assert [s["tags"] for s in line["stops"]] == [1, 2, 7, 8]
    assert r["following"] == 1 and r["stops"] == ["rooted", "ladder", "movement", "roaming"]


def test_broad_tags_stay_out(legacy_db):
    """Black Metal's only parent is Metal, a broad tag: roaming leaves it out, so the line never takes all of Metal.
    Blackgaze comes in through Atmospheric Black Metal; Shoegaze's 0.4 on 103 is under the line."""
    line = reach.reach_from_query(legacy.connect(legacy_db), "b=style:black metal&n=20")["lines"][0]
    assert _counts(line) == [("rooted", 2, 0), ("ladder", 2, 0), ("movement", 2, 0), ("roaming", 2, 0)]
    keys = {x["key"] for s in line["stops"] for x in s["new_tags"]}
    assert "metal" not in keys and {"blackgaze", "shoegaze"} <= keys
    assert {x["movement"] for x in line["stops"][2]["new_tags"]} == {"blackgaze"}


def test_rooted_is_the_junction(legacy_db):
    """The rooted stop is the line as it is, for every fixture tree with a style condition; and asking for the reach
    leaves the Junction's answer exactly as it was."""
    conn = legacy.connect(legacy_db)
    trees = [playlists.tree_of(playlists._get(conn, "blend-black-metal-doom-metal")), rules.from_query(DOOM),
             rules.from_query("b=style:doom metal,mood:sad~5&b=(style:black metal|decade:2020s)~5&n=10")]
    def build(tree):
        out = junction.build(conn, tree)
        out["picked"].pop("seconds")  # how long the picking took
        return out
    for tree in trees:
        before = build(tree)
        r = reach.reach(conn, tree)
        assert build(tree) == before
        for line, x in zip(before["lines"], r["lines"]):
            assert x["stops"] and x["stops"][0]["count"] == line["count"], (tree, x["id"])
            assert all(a["count"] <= b["count"] for a, b in zip(x["stops"], x["stops"][1:]))  # each takes in the last


def test_what_is_followed(legacy_db):
    """Only a style condition the line needs: not one under NOT (that would shrink the line), not another field."""
    conn = legacy.connect(legacy_db)
    r = reach.reach_from_query(conn, "b=decade:2010s,!style:black metal~5&b=mood:sad~5&n=10")
    assert [x["stops"] for x in r["lines"]] == [[], []] and r["following"] == 0
    r = reach.reach_from_query(conn, "b=(style:doom metal|style:black metal)~10&n=10")
    line = r["lines"][0]
    assert [f["path"] for f in line["follows"]] == ["all.0.any.0", "all.0.any.1"]
    # 101-104 at rooted; Dark Ambient's 101 is already in, so nothing is added.
    assert _counts(line) == [("rooted", 4, 0), ("ladder", 4, 0), ("movement", 4, 0), ("roaming", 4, 0)]
    r = reach.reach_from_query(conn, "b=style:not a tag at all~10&n=10")
    assert r["lines"][0]["stops"] == []  # on no ladder and in no movement: nothing to follow


def test_rows_behind_every_stop(client):
    r = client.get(f"/api/junction/reach?{DOOM}").json()
    for s in r["lines"][0]["stops"]:
        for which in ("count", "added"):
            rows = client.get(f"/api/junction/reach/rows?{DOOM}&line=a&stop={s['stop']}&which={which}").json()
            assert rows["count"] == s[which], (s["stop"], which)
    added = client.get(f"/api/junction/reach/rows?{DOOM}&line=a&stop=movement&which=added").json()
    assert [x["rating_key"] for x in added["rows"]] == [101]
    every = client.get(f"/api/junction/reach/rows?{DOOM}&line=a&stop=roaming").json()
    assert [x["rating_key"] for x in every["rows"]] == [101, 104, 103]  # album order (artist, year, album)
    assert client.get(f"/api/junction/reach/rows?{DOOM}&line=a&stop=far").status_code == 400
    assert client.get(f"/api/junction/reach/rows?{DOOM}&line=a&stop=ladder&which=nope").status_code == 400
    assert client.get(f"/api/junction/reach/rows?{DOOM}&line=zz&stop=ladder").status_code == 404
    assert client.get("/api/junction/reach/rows?b=decade:2010s&line=a&stop=ladder").status_code == 404
    assert client.get("/api/junction/reach?b=nope:x").status_code == 400


def test_reads_only(client, legacy_db):
    before = legacy_db.read_bytes()
    for url in (f"/api/junction/reach?{DOOM}", f"/api/junction/reach/rows?{DOOM}&line=a&stop=roaming&which=added"):
        assert client.get(url).status_code == 200, url
    assert legacy_db.read_bytes() == before
