"""The vendored jimbo-dj functions give the match keys jimbo-dj stored (fixture rows copy its shape)."""

from traqfreq import legacy
from traqfreq.vendor import jimbodj_history as jd


def test_match_keys_agree_with_stored(legacy_db):
    conn = legacy.connect(legacy_db)
    rows = conn.execute("SELECT artist, title, match_key FROM listens").fetchall()
    assert rows and all(jd.match_key(r["artist"], r["title"]) == r["match_key"] for r in rows)


def test_norm_rules():
    assert jd.match_key("The Paper Lanterns", "Static Gulls (Remastered 2024)") == "paperlanterns|staticgulls"
    assert jd.match_key("Ada Vey feat. Someone", "Coil - Live at Home") == "adavey|coil"
    assert jd.norm_artist("Sigur Rós") == "sigurros" and jd.norm_artist("!!!") == "!!!"
    assert jd.band_of(23) == "night" and jd.band_of(6) == "morning"
    assert jd.PRIORITY[0] == "lastfm" and jd.MIN_PLAY_MS == 30_000
