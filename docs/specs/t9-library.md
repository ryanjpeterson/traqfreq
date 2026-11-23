# T9–T12: LIBRARY, read-only (P2)

**Gate:** counts match jimbo-dj. Every LIBRARY number traqfreq shows equals the number jimbo-dj shows for the same data, says which rule it uses (W3) and can show its rows. As in P1, the gate compares with what jimbo-dj stored in its `stats` table (`library.stats`, `library.charts`), with a script and an endpoint.

traqfreq only reads. jimbo-dj keeps every library write (Plex sync, the analyzer, file checks, Fix in Plex, MusicBrainz lookups) until LIBRARY's cut-over in P6. Audio files are never opened by traqfreq in P2.

## How jimbo-dj counts (read at jimbo-dj 1d8a7cb; re-read before T9)
Source: `src/jimbodj/library.py` (`stats`), `statcache.py` (`library.stats`, `library.charts`), `insights.py` (`_all_views`, `_release_years`), `live.py` (`distributions`), `facets.py`, `browse.py`, `routes/library.py`, `routes/entities.py`, `history.py` (`plays_of`, `track_stats`).

- **Live track:** `tracks.removed_at IS NULL` (the last Plex sync still saw it). Every LIBRARY count is over live tracks unless it says otherwise.
- **Tracks / albums / artists:** `COUNT(*)`, `COUNT(DISTINCT album_key)`, `COUNT(DISTINCT artist_key)` of live tracks (already in SETUP's measures since T5).
- **Hours / size:** `SUM(duration_ms) / 3 600 000` rounded to 0.1; `SUM(file_size) / 1e9` rounded to 0.1.
- **Codecs, containers:** top 10 by tracks (`COALESCE(col, '?')`); **bitrate buckets** `<192k`, `192-255k`, `256-319k`, `320k`, `>320k (lossless)` on `bitrate` (kbps, half-open ranges).
- **Play history in the library:** `view_count > 0` (played tracks, %), `SUM(view_count)`, `user_rating IS NOT NULL` (rated), Plex top artists by `SUM(view_count)` grouped by `artist_key`.
- **A track's plays** anywhere outside HISTORY: `max(Plex view_count, history plays)`, never the sum (`history.plays_of`). Vendor `plays_of` / `last_of` unchanged.
- **Analysed:** `sonic_version IS NOT NULL` (Plex sonic analysis) vs jimbo-dj's own analyzer (`analysis.status = 'ok'` at the current analyzer version, `features` row). Say which one each number is.
- **Paths:** `local_path IS NOT NULL` (mapped), `parts > 1`, removed since the first sync (`removed_at IS NOT NULL`). `paths.folders` and `readable_here` depend on jimbo-dj's config and its disk: **not compared** (traqfreq can't see jimbo-dj's mounts); shown as jimbo-dj stored them.
- **Charts** (`library.charts`): files, time (added/released), place, genres and sound distributions. Genres and styles are TAGS (P4): not compared in P2, shown as "with TAGS".

## Reuse
Vendor what counting needs, unchanged, into `src/traqfreq/vendor/jimbodj_library.py` with `VENDORED_FROM` (the commit): `_pct`, the bitrate buckets, `plays_of`, `last_of`, and any pure helpers `insights._all_views` / `facets` use for the non-genre charts. Never rewrite them; if one needs jimbo-dj's `Settings` or a connection helper, give it a stand-in next to the copy (as T8 did for `listen_tz`).

## Sessions
### T9: library numbers and the rows behind them
- Fixture: extend `scripts/make_fixture.py` with invented tracks so each rule differs from a raw count (a lossless and a 128k file, a two-part track, an unmapped path, a rated track, a played one with `view_count` and history plays both set, so `plays_of` takes the max). Add a stored `library.stats` row with the full shape (keep T5–T8's counts: add tracks on new albums/artists only if SETUP's tests are updated to the new expected numbers, or add the new tracks as `removed_at` set where a rule needs it).
- `src/traqfreq/library.py`: `stats(conn)` = jimbo-dj's `library.stats` minus the config-dependent folder checks; `tracks(conn, filters)` = the rows behind each number (codec, container, bitrate bucket, played, rated, analysed, mapped, multi-part, removed), paged.
- API: `GET /api/library/stats`, `GET /api/library/tracks?…` (cached in traqfreq's store, keyed by `last_sync`, `history_version`, analyzer version).
### T10: LIBRARY page
- `/library`: headline counts (tracks, albums, artists, hours, size), files (codecs, containers, bitrate: drawings with a list view and summary, L6), play history (played %, Plex plays, rated, Plex top artists), analysis (Plex sonic vs jimbo-dj's analyzer), paths. Every number opens its rows (`/library/tracks?…`, `StationRow`s with key/BPM where analysed). Phone and tablet as in T6.
### T11: Albums, artists, a track
- Album and artist lists (sort by name, plays (`plays_of`), added, year), an album page (tracks in disc/track order, its plays), an artist page (albums, top tracks, plays), a track page (file facts, analysis, plays by source from HISTORY). Read `routes/entities.py` for what jimbo-dj shows and match its numbers.
### T12: gate
- `scripts/p2_gate.py` (read-only, like `p1_gate.py`: `--url` or `--db`): every field of jimbo-dj's stored `library.stats` (and the non-genre parts of `library.charts`) next to traqfreq's, with `matches` and freshness (statcache stamps: `library.stats` = `[last_sync, history_version]`). `GET /api/library/compare`, shown on SETUP and LIBRARY.
- Gate run on the Mac mini (live data) over the deployed API; record it in HANDOFF.

## Not in P2
Plex sync, analysis runs, file checks on disk, Fix in Plex, MusicBrainz: writes or disk access, P6. Genres, styles and tag ladders: TAGS (P4). Playlists and mixes (P5, P7).
