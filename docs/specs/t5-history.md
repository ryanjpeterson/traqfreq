# T5–T8: HISTORY, read-only (P1)

**Gate:** counts match jimbo-dj. Every HISTORY number traqfreq shows equals the number jimbo-dj shows for the same data, and each says which rule it uses (W3) and can show its rows.

traqfreq only reads. jimbo-dj keeps every history write (imports, dedupe, rematch, time zone setting) until HISTORY's cut-over in P6.

## How jimbo-dj counts (read at jimbo-dj 1d8a7cb)
Source: `src/jimbodj/history.py` (module doc, `dedupe`, `_overview`, `_plays`, `Names`), `statcache.py`, `schedule.py`.

- **Listens** (`listens`): one row per imported listen from Last.fm, Plex, Spotify, Apple Music. Unique on `(source, started_at, match_key)`. `started_at` is UTC epoch seconds.
- **Play** = `counted = 1`. jimbo-dj sets the flag after each import (`dedupe`); traqfreq reads it and never recomputes it. A listen that isn't a play is exactly one of:
  - too short: under 30 s (`counted = 0`, `dup_of IS NULL`);
  - repeat: the same source logged it twice within 30 s (`dup_of = source`);
  - duplicate: a source ahead in `PRIORITY` (Last.fm, Plex, Spotify, Apple Music) has the same play within its window (`dup_of` = that source).
  So plays + too short + repeats + duplicates = listens. `overview.adds_up` checks it on every read. **Nothing counts twice.**
- **Library track of a play:** `COALESCE(listens.rating_key, listen_matches.rating_key)`; NULL means not in the library. "Matched %" is plays with a track / plays.
- **Songs:** rows of `listen_matches` (distinct normalised artist|title heard); matched = those with a `rating_key`.
- **Time zone:** years, months, days, hours are in meta `history_tz`, else `TZ`, else America/Denver. traqfreq does the same (`Settings.tz` from `TZ`; compose sets `TZ`).
- **Names:** one name per artist, song and album however each source spelled it (`history.Names`: library spelling first, else the most played). Top lists count by these names.
- **Minutes:** `ms_played`, except Last.fm (track length) and Apple Music's daily summary (capped at the track length); no length at all: 225 s (`_minutes`).
- **A track's plays** elsewhere (Library, mixes): `max(Plex view_count, history plays)`, never the sum (`plays_of`).
- **jimbo-dj's own numbers** are stored as JSON in its `stats` table (`statcache.py`): `history.overview` (params `''`), `history.wrapped` (params `2025`, `2025-06`, `2025-06-14`), `library.stats`. They are rebuilt hourly and after imports, so they can lag the listens by up to an hour. traqfreq reads them as the comparison for the gate (`jimbodj` fields); when they differ, compare after jimbo-dj's next rebuild (`stats.stamp` = meta `history_version` when fresh).

## Reuse: vendored
jimbo-dj's repo is private, so a pinned git dependency would need credentials in CI and in the image. The pure functions are copied unchanged into `src/traqfreq/vendor/jimbodj_history.py` (constants, `band_of`, `norm_artist`, `norm_title`, `match_key`), with the commit they came from. `tests/test_vendor.py` checks them against the match keys jimbo-dj stored. Anything else T6–T8 need (`Names`, `_minutes`, dedupe windows, period ranges) is vendored the same way, never rewritten.

## Sessions
### T5 (done): schema, counting rules, first read API
- Fixture and `legacy.KEY_TABLES` match jimbo-dj's real schema (`tracks` by `rating_key` with `removed_at`, `albums`/`artists` by key, `analysis`, `features`, `listens`, `listen_matches`, `history_imports`, `stats`). Invented rows chosen so each rule differs from a raw count.
- `/api/legacy/summary` adds `measures`: tracks, albums, artists, plays, each with its SQL rule, jimbo-dj's stored value and `matches`. `counts` (raw rows) stays. SETUP shows both.
- `GET /api/history/overview`: plays, listens, the three non-play reasons, `adds_up`, matched plays, songs, per source (in PRIORITY order) and per year (in the listening time zone), rules, jimbo-dj's stored plays.
- `GET /api/history/listens?status=play|too_short|repeat|duplicate&source=&year=&limit=&offset=`: the rows behind each number, newest first, with the rule and its parameters.

### T6 (done): Overview
Built as below; details in HANDOFF (T6 done). Heatmap levels: 0 = no plays, 1–4 = quarters of the shown days with plays. Rows page: `/history/listens` with the API's filters.
- Module H page (shown when `TRAQFREQ_MODULES` has H): plays headline, the year heatmap (a year of days, plays per day in the listening time zone), top artists (vendor `Names`, so one name per artist), sources table (listens, plays, too short, repeats, duplicates of whom), years with plays per source, matched %. Every number has a note with its rule and opens its rows (`/api/history/listens`, paged).
- A stats cache in traqfreq's own database (`TRAQFREQ_DATA_DIR`, never the legacy DB): built summaries keyed by jimbo-dj's meta `history_version` and the time zone, rebuilt when either changes. The overview loops over every play (350,953 listens live), so pages read the cache.
- Kit only (K1), copy in `strings.json` (W1); phone and tablet layouts; Vitest.

### T7: Counted once
- Duplicates and repeats with their reasons: for each listen that isn't a play, the play it duplicates (same `match_key`, the winning source, within jimbo-dj's window: `DEDUPE_SECONDS`, `REPEAT_SECONDS`, `window_sql`; vendored) and how far apart they were.
- Held bursts and new bot checks, **read-only**: traqfreq flags patterns jimbo-dj doesn't (bursts of plays too close together to have been heard, one song looped, scrobbler-bot shapes), each with its reason and rows. They are reports only: the play count stays jimbo-dj's (`counted = 1`) until HISTORY's cut-over, so the gate still holds. Proposed rules go in this session's spec addition first.

### T8: Years, Wrapped, This day, Top
- Vendor `_minutes` and the period ranges. Years (plays and hours), Wrapped for a year, month or day, On this day, Top artists / songs / albums for a period (`all`, `30d`, `12m`, `YYYY`, `YYYY-MM`) by plays or minutes.
- Gate script (`scripts/p1_gate.py`, read-only): every stored jimbo-dj history number (`stats.history.overview`, every `stats.history.wrapped` row) next to traqfreq's for the same period, with `matches`. Also `GET /api/history/compare` for SETUP and HISTORY.
- Gate run on the Mac mini (live data): all match, or each difference explained by a stale stored row. Record it in HANDOFF.

## Not in P1
Imports, dedupe, rematch, the time zone setting, Last.fm sync: all writes, P6. Library counts (P2) beyond SETUP's four measures.
